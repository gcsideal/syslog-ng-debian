/*
 * Copyright (c) 2018 Balabit
 * Copyright (c) 2013 Balázs Scheidler <balazs.scheidler@balabit.com>
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 as published
 * by the Free Software Foundation, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 *
 * As an additional exemption you are allowed to compile & link against the
 * OpenSSL libraries as published by the OpenSSL project. See the file
 * COPYING for details.
 *
 */

#include <criterion/criterion.h>
#include <criterion/parameterized.h>
#include <string.h>

/* NOTE: including the implementation file to access static functions */
#include "radix.c"

static gboolean
_invoke_parser(gboolean (*parser)(gchar *str, gint *len, const gchar *param, gpointer state, RParserMatch *match),
               const gchar *str, gpointer param, gpointer state, gchar **result_string)
{
  gboolean result;
  gint len = 0;
  gchar *dup = g_strdup(str);
  RParserMatch match;

  memset(&match, 0, sizeof(match));
  result = parser(dup, &len, param, state, &match);

  if (match.match)
    {
      if (result)
        *result_string = g_strdup(match.match);
    }
  else
    {
      match.ofs = 0 + match.ofs;
      match.len = (gint16) match.len + len;
      if (result)
        *result_string = g_strndup(&dup[match.ofs], match.len);
    }
  g_free(dup);
  return result;
}

/*
 * Criterion parameter payloads must be self-contained here.
 * We use fixed-size arrays (not pointers) to avoid pointer invalidation across
 * worker process boundaries on macOS.
 * has_* members preserve NULL-vs-set semantics for optional string fields.
 */
typedef struct _ParserTestParam
{
  gchar str[32];
  gchar param[32];
  gboolean has_param;
  gchar expected_string[32];
  gboolean has_expected_string;
  gboolean expected_result;
} ParserTestParam;

ParameterizedTestParameters(parser, test_string_parser)
{
  static ParserTestParam parser_params[] =
  {
    {.str = "foo", .param = "", .has_param = FALSE, .expected_string = "foo", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo bar", .param = "", .has_param = FALSE, .expected_string = "foo", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo123 bar", .param = "", .has_param = FALSE, .expected_string = "foo123", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo{}", .param = "", .has_param = FALSE, .expected_string = "foo", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo[]", .param = "", .has_param = FALSE, .expected_string = "foo", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo", .param = "X", .has_param = TRUE, .expected_string = "foo", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "foo=bar", .param = "=", .has_param = TRUE, .expected_string = "foo=bar", .has_expected_string = TRUE, .expected_result = TRUE},
    {.str = "", .param = "", .has_param = FALSE, .expected_string = "", .has_expected_string = FALSE, .expected_result = FALSE},
  };

  return cr_make_param_array(ParserTestParam, parser_params, G_N_ELEMENTS(parser_params));
}

ParameterizedTest(ParserTestParam *param, parser, test_string_parser)
{
  gchar *result_string = NULL;
  gboolean result;

  result = _invoke_parser(r_parser_string, param->str, param->has_param ? (gpointer) param->param : NULL, NULL,
                          &result_string);
  if (param->expected_result == TRUE)
    {
      cr_assert(result, "Mismatching parser result (true expected)");
      cr_assert(param->has_expected_string, "Expected parser output is missing");
      cr_assert_str_eq(result_string, param->expected_string, "Mismatching parser result (exp:%s, res:%s)",
                       param->expected_string, result_string);
      g_free(result_string);
    }
  else
    {
      cr_assert_not(result, "Mismatching parser result (false expected)");
    }
}

/*
 * Criterion parameter payloads must be self-contained here.
 * We use fixed-size arrays (not pointers) to avoid pointer invalidation across
 * worker process boundaries on macOS
 */
typedef struct _ParserQStringTestParam
{
  gchar str[32];
  gchar quotes[8];
  gchar expected_string[32];
} ParserQStringTestParam;

ParameterizedTestParameters(parser, test_qstring_parser)
{
  static ParserQStringTestParam parser_params[] =
  {
    {.str = "'foo'", .quotes = "''", .expected_string = "foo"},
    {.str = "\"foo\"", .quotes = "\"\"", .expected_string = "foo"},
    {.str = "{foo}", .quotes = "{}", .expected_string = "foo"},
  };

  return cr_make_param_array(ParserQStringTestParam, parser_params, G_N_ELEMENTS(parser_params));
}

static gpointer
_compile_qstring_state(const gchar *quotes)
{
  union
  {
    gpointer ptr;
    gchar ending_char;
  } state;

  memset(&state, 0, sizeof(state));
  state.ending_char = quotes[1];
  return state.ptr;
}

ParameterizedTest(ParserQStringTestParam *param, parser, test_qstring_parser)
{
  gchar *result_string = NULL;
  gboolean result;

  result = _invoke_parser(r_parser_qstring, param->str, param->quotes, _compile_qstring_state(param->quotes),
                          &result_string);
  cr_assert(result, "Mismatching parser result");
  cr_assert_str_eq(result_string, param->expected_string, "Mismatching parser result (exp:%s, res:%s)",
                   param->expected_string, result_string);
  g_free(result_string);
}
