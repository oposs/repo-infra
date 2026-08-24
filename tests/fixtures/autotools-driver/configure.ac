AC_INIT([selftest], [0.1])
AC_CONFIG_MACRO_DIRS([m4])
AM_INIT_AUTOMAKE([foreign])
REPO_INFRA_CONTAINER
AS_IF([test "x$enable_container" = xno], [
  AC_CHECK_PROG([PERL], [perl], [perl])
  AS_IF([test -z "$PERL"], [AC_MSG_ERROR([perl is required])])
])
AC_CONFIG_FILES([Makefile])
AC_OUTPUT
