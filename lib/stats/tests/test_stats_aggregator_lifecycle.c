/*
 * Copyright (c) 2026 One Identity
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 *
 * As an additional exemption you are allowed to compile & link against the
 * OpenSSL libraries as published by the OpenSSL project. See the file
 * COPYING for details.
 *
 */

/*
 * Lifecycle correctness tests for stats aggregators.
 *
 * Every test drives the aggregator through a lifecycle transition, then runs
 * iv_main() briefly.  A violation (freed aggregator with a still-queued timer)
 * surfaces as a crash, an ivykis warning, or an ASAN use-after-free.
 */

#include <criterion/criterion.h>

#include "apphook.h"
#include "mainloop.h"
#include "thread-utils.h"
#include "stats/stats.h"
#include "stats/stats-cluster.h"
#include "stats/stats-cluster-single.h"
#include "stats/stats-counter.h"
#include "stats/stats-registry.h"
#include "stats/aggregator/stats-aggregator.h"
#include "stats/aggregator/stats-aggregator-registry.h"
#include "timeutils/unixtime.h"
#include "timeutils/misc.h"

#include <iv.h>

static void
_setup(void)
{
  app_startup();
  /* Aggregator code paths assert main-thread context. */
  main_thread_handle = get_thread_id();

  StatsOptions opts;
  stats_options_defaults(&opts);
  opts.level = 3;
  stats_reinit(&opts);
}

static void
_teardown(void)
{
  app_shutdown();
}

TestSuite(stats_aggregator_lifecycle, .init = _setup, .fini = _teardown);

static void
_iv_quit_cb(void *user_data)
{
  iv_quit();
}

/* Pump the ivykis main loop briefly with a bounded sentinel timer.  Any
 * update_timer that is still queued and whose expiry has elapsed will be
 * dispatched before the quit timer fires. */
static void
_pump_iv_main(gint quit_after_ms)
{
  struct iv_timer quit_timer;
  IV_TIMER_INIT(&quit_timer);
  quit_timer.cookie = NULL;
  quit_timer.handler = _iv_quit_cb;

  iv_validate_now();
  quit_timer.expires = iv_now;
  timespec_add_msec(&quit_timer.expires, quit_after_ms);

  iv_timer_register(&quit_timer);
  iv_main();

  if (iv_timer_registered(&quit_timer))
    iv_timer_unregister(&quit_timer);
}

static StatsCounterItem *
_register_input_counter(StatsClusterKey *input_key, const gchar *id, const gchar *instance)
{
  StatsCounterItem *counter = NULL;

  stats_lock();
  stats_cluster_logpipe_key_legacy_set(input_key, SCS_DESTINATION, id, instance);
  stats_register_counter(0, input_key, SC_TYPE_PROCESSED, &counter);
  stats_unlock();

  cr_assert_not_null(counter);
  return counter;
}

static void
_unregister_input_counter(StatsClusterKey *input_key, StatsCounterItem **counter)
{
  stats_lock();
  stats_unregister_counter(input_key, SC_TYPE_PROCESSED, counter);
  stats_unlock();
}

static StatsAggregator *
_register_cps(StatsClusterKey *input_key, const gchar *id, const gchar *instance)
{
  StatsClusterKey out_key;
  StatsAggregator *cps = NULL;

  stats_cluster_single_key_legacy_set_with_name(&out_key, SCS_DESTINATION,
                                                id, instance, "eps");

  stats_aggregator_lock();
  stats_register_aggregator_cps(0, &out_key, input_key, SC_TYPE_PROCESSED, &cps);
  stats_aggregator_unlock();

  cr_assert_not_null(cps);
  return cps;
}

static void
_drop_cps_reference(StatsAggregator **cps)
{
  stats_aggregator_lock();
  stats_unregister_aggregator(cps);
  stats_aggregator_unlock();
}

static void
_reset_registry(void)
{
  stats_aggregator_lock();
  stats_lock();
  stats_aggregator_registry_reset();
  stats_unlock();
  stats_aggregator_unlock();
}

static void
_remove_orphans(void)
{
  stats_aggregator_lock();
  stats_aggregator_remove_orphaned_stats();
  stats_aggregator_unlock();
}

/* Force the update_timer to expire on the next iv_main tick (instead of
 * waiting for the configured period).  Call while the aggregator is alive. */
static void
_force_timer_to_fire_immediately(StatsAggregator *aggr)
{
  iv_validate_now();
  aggr->update_timer.expires = iv_now;
}

Test(stats_aggregator_lifecycle, drop_reference_leaves_subsystem_safe_for_iv_main)
{
  StatsClusterKey input_key;
  StatsCounterItem *input_counter = _register_input_counter(&input_key, "drop-id", "drop-inst");

  StatsAggregator *cps = _register_cps(&input_key, "drop-id", "drop-inst");
  cr_assert(iv_timer_registered(&cps->update_timer));

  _drop_cps_reference(&cps);

  _pump_iv_main(50);

  _unregister_input_counter(&input_key, &input_counter);
}

Test(stats_aggregator_lifecycle, reset_then_remove_orphans_must_not_leave_dangling_timer)
{
  StatsClusterKey input_key;
  StatsCounterItem *input_counter = _register_input_counter(&input_key, "reset-id", "reset-inst");

  StatsAggregator *cps = _register_cps(&input_key, "reset-id", "reset-inst");
  StatsAggregator *cps_ref = cps;

  _drop_cps_reference(&cps);
  _reset_registry();

  /* Pre-stage timer so a stale dispatch happens within _pump_iv_main below,
   * not after the test ends. */
  if (iv_timer_registered(&cps_ref->update_timer))
    _force_timer_to_fire_immediately(cps_ref);

  _remove_orphans();
  /* cps_ref is dangling from here on. */

  _pump_iv_main(50);

  _unregister_input_counter(&input_key, &input_counter);
}

Test(stats_aggregator_lifecycle, registry_deinit_must_release_armed_aggregators_safely)
{
  StatsClusterKey input_key;
  StatsCounterItem *input_counter = _register_input_counter(&input_key, "deinit-id", "deinit-inst");

  StatsAggregator *cps = _register_cps(&input_key, "deinit-id", "deinit-inst");
  StatsAggregator *cps_ref = cps;

  _drop_cps_reference(&cps);
  _reset_registry();

  if (iv_timer_registered(&cps_ref->update_timer))
    _force_timer_to_fire_immediately(cps_ref);

  _unregister_input_counter(&input_key, &input_counter);

  stats_destroy();
  /* cps_ref is dangling now. */

  /* Re-initialize so suite teardown (app_shutdown) stays balanced. */
  stats_init();

  _pump_iv_main(50);
}

Test(stats_aggregator_lifecycle, re_register_after_reset_yields_single_active_timer)
{
  StatsClusterKey input_key;
  StatsCounterItem *input_counter = _register_input_counter(&input_key, "rereg-id", "rereg-inst");

  StatsAggregator *cps = _register_cps(&input_key, "rereg-id", "rereg-inst");
  cr_assert(iv_timer_registered(&cps->update_timer));

  _drop_cps_reference(&cps);
  _reset_registry();

  StatsAggregator *cps2 = _register_cps(&input_key, "rereg-id", "rereg-inst");
  cr_assert(iv_timer_registered(&cps2->update_timer),
            "re-registered aggregator must have an armed update_timer");

  _drop_cps_reference(&cps2);

  _pump_iv_main(50);

  _unregister_input_counter(&input_key, &input_counter);
}
