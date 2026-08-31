/*
 * Copyright (c) 2025 Romain Tartière
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

#include "filter/filter-expr.h"
#include "filter/filter-blank.h"
#include "cfg.h"
#include "test_filters_common.h"

#include <criterion/criterion.h>
#include <criterion/parameterized.h>
#include <glib.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

LogMessage *
_construct_sample_message(void)
{
  LogMessage *msg = log_msg_new_empty();

  msg->pri = 15;
  log_msg_set_value(msg, LM_V_PROGRAM, "software", -1);
  log_msg_set_value_by_name_with_type(msg, "emptystrvalue", "", -1, LM_VT_STRING);
  log_msg_set_value_by_name_with_type(msg, "blankstrvalue", "   \t\t  ", -1, LM_VT_STRING);
  log_msg_set_value_by_name_with_type(msg, "strvalue", "string", -1, LM_VT_STRING);
  log_msg_set_value_by_name_with_type(msg, "jsonvalue", "{\"foo\":\"foovalue\"}", -1, LM_VT_JSON);
  log_msg_set_value_by_name_with_type(msg, "truevalue", "1", -1, LM_VT_BOOLEAN);
  log_msg_set_value_by_name_with_type(msg, "falsevalue", "0", -1, LM_VT_BOOLEAN);
  log_msg_set_value_by_name_with_type(msg, "int32value", "32", -1, LM_VT_INTEGER);
  log_msg_set_value_by_name_with_type(msg, "int64value", "4294967296", -1, LM_VT_INTEGER);
  log_msg_set_value_by_name_with_type(msg, "nanvalue", "nan", -1, LM_VT_DOUBLE);
  log_msg_set_value_by_name_with_type(msg, "dblvalue", "3.1415", -1, LM_VT_DOUBLE);
  log_msg_set_value_by_name_with_type(msg, "datevalue", "1653246684.123", -1, LM_VT_DATETIME);
  log_msg_set_value_by_name_with_type(msg, "emptylistvalue", "", -1, LM_VT_LIST);
  log_msg_set_value_by_name_with_type(msg, "listvalue", "foo,bar,baz", -1, LM_VT_LIST);
  log_msg_set_value_by_name_with_type(msg, "nullvalue", "", -1, LM_VT_NULL);
  log_msg_set_value_by_name_with_type(msg, "bytesvalue", "\0\1\2\3", 4, LM_VT_BYTES);
  log_msg_set_value_by_name_with_type(msg, "protobufvalue", "\4\5\6\7", 4, LM_VT_PROTOBUF);
  log_msg_set_value_by_name_with_type(msg, "nested.empty.value", "", -1, LM_VT_STRING);
  return msg;
}

/* Use the setup and teardown functions provided in test_filters_common.h */
TestSuite(filter, .init = setup, .fini = teardown);

/*
 * Criterion parameter payloads must be self-contained here.
 * We use fixed-size arrays (not pointers) to avoid pointer invalidation across
 * worker process boundaries on macOS
 */
typedef struct _FilterParamBlank
{
  gchar name[64];
  gboolean expected_result;
} FilterParamBlank;

ParameterizedTestParameters(filter, test_filter_blank)
{
  static FilterParamBlank test_data_list[] =
  {
    {.name = "emptystrvalue",      .expected_result = TRUE},
    {.name = "blankstrvalue",      .expected_result = TRUE},
    {.name = "strvalue",           .expected_result = FALSE},
    {.name = "jsonvalue",          .expected_result = FALSE},
    {.name = "truevalue",          .expected_result = FALSE},
    {.name = "falsevalue",         .expected_result = TRUE},
    {.name = "int32value",         .expected_result = FALSE},
    {.name = "int64value",         .expected_result = FALSE},
    {.name = "nanvalue",           .expected_result = FALSE},
    {.name = "dblvalue",           .expected_result = FALSE},
    {.name = "datevalue",          .expected_result = FALSE},
    {.name = "emptylistvalue",     .expected_result = TRUE},
    {.name = "listvalue",          .expected_result = FALSE},
    {.name = "nullvalue",          .expected_result = TRUE},
    {.name = "bytesvalue",         .expected_result = FALSE},
    {.name = "protobufvalue",      .expected_result = FALSE},
    {.name = "nested",             .expected_result = FALSE},
    {.name = "nested.empty",       .expected_result = FALSE},
    {.name = "nested.empty.value", .expected_result = TRUE},
  };

  return cr_make_param_array(FilterParamBlank, test_data_list, G_N_ELEMENTS(test_data_list));
}

ParameterizedTest(FilterParamBlank *param, filter, test_filter_blank)
{
  LogMessage *msg = _construct_sample_message();
  FilterExprNode *filter = filter_blank_new(param->name);
  testcase_with_message(msg, param->name, filter, param->expected_result);
  log_msg_unref(msg);
}

/*
 * Regression test for https://github.com/syslog-ng/syslog-ng/issues/5679
 *
 * FilterBlank used to store the per-evaluation result in a shared struct
 * field, causing a race when multiple worker threads evaluated the same node
 * concurrently: one thread could read another thread's result.
 */

#define BLANK_RACE_N_THREADS    16
#define BLANK_RACE_N_ITERATIONS 4096

typedef struct _FilterBlankRaceThreadData
{
  FilterExprNode *filter;
  gboolean errors;
} FilterBlankRaceThreadData;

static gpointer
_filter_blank_race_thread(gpointer user_data)
{
  FilterBlankRaceThreadData *data = (FilterBlankRaceThreadData *) user_data;
  data->errors = FALSE;

  for (gint i = 0; i < BLANK_RACE_N_ITERATIONS; i++)
    {
      /* Alternate: even iterations have the field, odd ones do not */
      LogMessage *msg = log_msg_new_empty();
      gboolean field_present = (i % 2 == 0);

      if (field_present)
        log_msg_set_value_by_name_with_type(msg, "racetest", "1.2.3.4", -1, LM_VT_STRING);

      gboolean result = filter_expr_eval(data->filter, msg);

      /* blank() should return TRUE when the field is absent, FALSE when present */
      if (result != !field_present)
        {
          data->errors = TRUE;
          log_msg_unref(msg);
          break;
        }

      log_msg_unref(msg);
    }

  return NULL;
}

Test(filter, test_filter_blank_thread_safety)
{
  FilterExprNode *f = filter_blank_new("racetest");
  cr_assert(filter_expr_init(f, configuration), "Filter init failed");

  GThread *threads[BLANK_RACE_N_THREADS];
  FilterBlankRaceThreadData thread_data[BLANK_RACE_N_THREADS];

  for (gint i = 0; i < BLANK_RACE_N_THREADS; i++)
    {
      thread_data[i].filter = f;
      threads[i] = g_thread_new("filter-blank-race", _filter_blank_race_thread, &thread_data[i]);
    }

  gboolean any_errors = FALSE;
  for (gint i = 0; i < BLANK_RACE_N_THREADS; i++)
    {
      g_thread_join(threads[i]);
      if (thread_data[i].errors)
        any_errors = TRUE;
    }

  filter_expr_unref(f);
  cr_assert_not(any_errors,
                "Thread-safety test failed: filter_blank_eval produced incorrect results under concurrent access");
}
