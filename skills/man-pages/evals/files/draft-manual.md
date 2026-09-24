---
title: MYTOOL
section: 1
header: mytool manual
footer: mytool 0.3.1
---

# NAME

mytool - forward mail to a relay

# Options

| Option | What it does |
|---|---|
| `--listen ADDR` | The address the proxy listens on. Defaults to 127.0.0.1:2525, which is what most local setups will want anyway. |
| `--relay HOST` | The upstream relay every message is forwarded to after the policy checks have passed. |
| `-v`, `--verbose` | Print every SMTP command and reply to standard error. |

# EXAMPLES

    mytool --listen 0.0.0.0:25 --relay mail.example.org

# DESCRIPTION

mytool accepts SMTP connections and forwards each message to a relay.

# SYNOPSIS

**mytool** [*OPTIONS*]
