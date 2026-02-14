Feature: Daemon protocol validation
  As a Kanbus maintainer
  I want protocol version checks to reject incompatible clients
  So that daemon communication is safe

  Scenario: Protocol version parsing rejects invalid strings
    When I parse protocol versions "1" and "bad"
    Then protocol parsing should fail with "invalid protocol version"

  Scenario: Protocol version parsing rejects non-numeric parts
    When I parse protocol versions "1.bad" and "1.0"
    Then protocol parsing should fail with "invalid protocol version"

  Scenario: Protocol version parsing rejects extra parts
    When I parse protocol versions "1.2.3" and "1.0"
    Then protocol parsing should fail with "invalid protocol version"

  Scenario: Protocol compatibility rejects mismatched major versions
    When I validate protocol compatibility for client "2.0" and daemon "1.0"
    Then protocol validation should fail with "protocol version mismatch"

  Scenario: Protocol compatibility rejects unsupported minor versions
    When I validate protocol compatibility for client "1.2" and daemon "1.0"
    Then protocol validation should fail with "protocol version unsupported"
