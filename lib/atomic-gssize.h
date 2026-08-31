/*
 * Copyright (c) 2002-2018 Balabit
 * Copyright (c) 2018 Laszlo Budai <laszlo.budai@balabit.com>
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

#ifndef ATOMIC_GSSIZE_H_INCLUDED
#define ATOMIC_GSSIZE_H_INCLUDED

#include "syslog-ng.h"

G_STATIC_ASSERT(sizeof(gssize) == sizeof(gpointer));

typedef struct
{
  gssize value;
} atomic_gssize;

/*
 * All atomic operations below use __atomic_* compiler builtins directly.
 *
 * The GLib g_atomic_pointer_* macros expect gpointer * storage, but our
 * value is gssize.  Using those macros causes type-mismatch errors across
 * different GLib/compiler combinations (strict-aliasing, -Wincompatible-
 * pointer-types, -Wint-conversion).  The __atomic_* builtins are available
 * on GCC 4.7+ and Clang 3.1+ and accept any scalar type, so they are the
 * portable, type-safe alternative.
 */

static inline gssize
atomic_gssize_add(atomic_gssize *a, gssize add)
{
  return (gssize) __atomic_fetch_add(&a->value, add, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_sub(atomic_gssize *a, gssize sub)
{
  return (gssize) __atomic_fetch_sub(&a->value, sub, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_inc(atomic_gssize *a)
{
  return (gssize) __atomic_fetch_add(&a->value, 1, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_dec(atomic_gssize *a)
{
  return (gssize) __atomic_fetch_sub(&a->value, 1, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_get(atomic_gssize *a)
{
  return (gssize) __atomic_load_n(&a->value, __ATOMIC_SEQ_CST);
}

static inline void
atomic_gssize_set(atomic_gssize *a, gssize value)
{
  __atomic_store_n(&a->value, value, __ATOMIC_SEQ_CST);
}

static inline gsize
atomic_gssize_get_unsigned(atomic_gssize *a)
{
  return (gsize) __atomic_load_n(&a->value, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_racy_get(atomic_gssize *a)
{
  return a->value;
}

static inline gsize
atomic_gssize_racy_get_unsigned(atomic_gssize *a)
{
  return (gsize) a->value;
}

static inline void
atomic_gssize_racy_set(atomic_gssize *a, gssize value)
{
  a->value = value;
}

static inline gsize
atomic_gssize_or(atomic_gssize *a, gsize value)
{
  return (gsize) __atomic_fetch_or(&a->value, value, __ATOMIC_SEQ_CST);
}

static inline gsize
atomic_gssize_xor(atomic_gssize *a, gsize value)
{
  return (gsize) __atomic_fetch_xor(&a->value, value, __ATOMIC_SEQ_CST);
}

static inline gsize
atomic_gssize_and(atomic_gssize *a, gsize value)
{
  return (gsize) __atomic_fetch_and(&a->value, value, __ATOMIC_SEQ_CST);
}

static inline gboolean
atomic_gssize_compare_and_exchange(atomic_gssize *a, gssize oldval, gssize newval)
{
  return !!__atomic_compare_exchange_n(&a->value, &oldval, newval, FALSE,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

static inline gssize
atomic_gssize_set_and_get(atomic_gssize *a, gssize value)
{
  gssize oldval = atomic_gssize_get(a);

  while (!atomic_gssize_compare_and_exchange(a, oldval, value))
    {
      oldval = atomic_gssize_get(a);
    }

  return oldval;
}
#endif
