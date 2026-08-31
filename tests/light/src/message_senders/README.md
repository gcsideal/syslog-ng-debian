# Message Senders Module

## ⚠️ Legacy Backward Compatibility Module

**This module contains legacy message sender classes ported from a legacy functional test framework for backward compatibility purposes.**

These classes are **NOT** recommended for new tests. For new test development, use the modern light framework patterns instead.

---

## Purpose

This module provides message sender classes that replicate the exact behavior of the original 2007-2015 functional test framework. They are used **exclusively** for:

1. **Maintaining behavioral compatibility** with legacy test code patterns
2. **Testing low-level source drivers** that require direct socket/file manipulation
3. **Specific test scenarios** where Config API patterns are insufficient

---

## Available Classes

### `MessageSender` (Base Class)

Abstract base class providing:
- Session counter tracking across test runs
- RFC3164 and RFC5424 syslog message formatting
- Message repetition support

### `FileSender`

Sends messages to files or named pipes.

**Features:**
- Byte-by-byte or bulk writing
- Named pipe detection and handling
- Null-padding for 2048-byte padded pipes
- Automatic directory creation
- Custom termination sequences

**Example:**
```python
from src.message_senders import FileSender

sender = FileSender('log-pipe', repeat=100)
sender.sendMessages('test message')
```

### `SocketSender`

Sends messages via Unix domain or Internet sockets.

**Features:**
- Unix domain sockets (stream and datagram)
- Internet sockets (TCP and UDP)
- **SSL/TLS support** (see below)
- Byte-by-byte or bulk sending
- Automatic retry on ENOBUFS

**Example:**
```python
from socket import AF_INET
from src.message_senders import SocketSender

# TCP connection
sender = SocketSender(AF_INET, ('localhost', 5514), dgram=0, repeat=100)
sender.sendMessages('test message')

# TLS connection
ssl_sender = SocketSender(
    AF_INET, ('localhost', 6514), 
    dgram=0, ssl_enabled=1, repeat=100
)
ssl_sender.sendMessages('secure message')
```

---

## SSL/TLS Configuration

### ⚠️ Deprecated Protocol Used Intentionally

**`SocketSender` uses `ssl.PROTOCOL_TLSv1_2` (deprecated) for backward compatibility.**

#### Why Deprecated Protocol?

The old functional test framework used `ssl.PROTOCOL_TLSv1_2`, which:
- ❌ **Does NOT verify certificates by default**
- ❌ **Does NOT check hostnames**
- ✅ **Works with self-signed certificates without explicit configuration**

Modern `ssl.PROTOCOL_TLS_CLIENT` enforces security by default:
- ✅ **Verifies certificates by default**
- ✅ **Checks hostnames by default**
- ❌ **Requires explicit `check_hostname=False` and `verify_mode=CERT_NONE` for self-signed certs**
- ❌ **Python enforces:** "Cannot set verify_mode to CERT_NONE when check_hostname is enabled"

#### Implementation

```python
# In socket_sender.py
if not self.dgram and self.ssl_enabled:
    # Use deprecated PROTOCOL_TLSv1_2 for backward compatibility
    # with old test framework behavior.
    self.sock = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2).wrap_socket(self.sock)
```

**This deprecation warning is expected and acceptable** for maintaining test compatibility.

---

## When to Use This Module

### ✅ Use Message Senders When:

- Maintaining existing tests that use these patterns
- Replicating legacy test behavior for compatibility
- Testing multiple heterogeneous sources simultaneously (unix-socket + tcp + udp + tls + files)
- Low-level source driver testing requires direct socket/file manipulation

### ❌ Do NOT Use for New Tests

**For new test development, use modern light framework patterns:**

#### Modern Pattern 1: Config API + loggen

```python
def test_network_tls(config, syslog_ng, port_allocator, loggen, testcase_parameters):
    # Copy SSL certificates
    server_key_path = copy_shared_file(testcase_parameters, "server.key")
    server_cert_path = copy_shared_file(testcase_parameters, "server.crt")
    
    # Create TLS source with Config API
    network_source = config.create_network_source(
        ip="localhost",
        port=port_allocator(),
        transport="tls",
        flags="no-parse",
        tls={
            "key-file": server_key_path,
            "cert-file": server_cert_path,
            "peer-verify": '"optional-untrusted"',
        },
    )
    
    file_destination = config.create_file_destination(file_name="output.log")
    config.create_logpath(statements=[network_source, file_destination])
    
    syslog_ng.start(config)
    
    # Use loggen for sending messages
    loggen.start(
        network_source.options["ip"], 
        network_source.options["port"],
        use_ssl=True,
        number=10,
    )
```

**See:** `tests/light/functional_tests/source_drivers/network_source/test_network_transports.py`

#### Modern Pattern 2: example-msg-generator Source

```python
def test_parser(config, syslog_ng):
    # Generate messages internally
    generator_source = config.create_example_msg_generator_source(
        num=10,
        freq=0,  # Generate immediately
        template=config.stringify("<41>message content")
    )
    
    parser = config.create_csv_parser(columns=["col1", "col2"])
    file_destination = config.create_file_destination(file_name="output.log")
    
    config.create_logpath(statements=[generator_source, parser, file_destination])
    syslog_ng.start(config)
```

**See:** `TESTING_GUIDE.md` for comprehensive patterns

---

### Technical Debt

This module represents **technical debt** that should eventually be eliminated:

- [ ] Audit all usages of `FileSender`/`SocketSender`
- [ ] Migrate to modern patterns where possible
- [ ] Document remaining cases that genuinely need legacy behavior
- [ ] Consider deprecation timeline once all old tests are converted

---

## References

- **Modern patterns:** `tests/light/TESTING_GUIDE.md`
- **TLS examples:** `tests/light/functional_tests/source_drivers/network_source/test_network_transports.py`
- **Config API:** `tests/light/src/syslog_ng_config/`

---

## Contributing

**When adding new tests:**
- ❌ Do NOT use these classes for new functionality
- ✅ Use modern light framework patterns
- ✅ Consult `TESTING_GUIDE.md` for best practices
