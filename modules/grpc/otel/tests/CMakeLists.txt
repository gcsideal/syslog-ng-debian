if (NOT APPLE)
  add_unit_test (
    CRITERION
    TARGET test_otel_protobuf_parser
    SOURCES test-otel-protobuf-parser.cpp
    INCLUDES ${OTEL_PROTO_BUILDDIR}
    DEPENDS otel-cpp)

  add_unit_test (
    CRITERION
    TARGET test_otel_protobuf_formatter
    SOURCES test-otel-protobuf-formatter.cpp
    INCLUDES ${OTEL_PROTO_BUILDDIR}
    DEPENDS otel-cpp)

  add_unit_test (
    CRITERION
    TARGET test_syslog_ng_otlp
    SOURCES test-syslog-ng-otlp.cpp
    INCLUDES ${OTEL_PROTO_BUILDDIR}
    DEPENDS otel-cpp)

  # Criterion's <criterion/alloc.h> still references std::allocator<void>::const_pointer,
  # which was deprecated in C++17 and removed in C++20 (both libstdc++ and libc++ drop
  # the std::allocator<void> specialization). Pin these criterion-based C++ tests to
  # C++17 so the header keeps compiling regardless of the C++ standard otel-cpp itself
  # is built with.
  set_target_properties(
    test_otel_protobuf_parser
    test_otel_protobuf_formatter
    test_syslog_ng_otlp
    PROPERTIES
      CXX_STANDARD 17
      CXX_STANDARD_REQUIRED ON
      CXX_EXTENSIONS OFF)

endif ()
