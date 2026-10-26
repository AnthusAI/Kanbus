Feature: Issue Router host hygiene and credential handling
  As an operator
  I want the router to clean up after finished packages and never leak credentials
  So that worktrees and credential copies do not accumulate and transcripts stay safe to commit

  Scenario: Router worktrees live inside the repository's git common directory
    Given a router test repository
    Then the router worktree for package "kbs-hygiene" claim "claim-hygiene" should be inside the git common directory

  Scenario: Resolving the worktree directory outside a git repository fails clearly
    Given an empty directory outside any git repository
    Then resolving the router worktree directory should fail with "router worktree directory could not be resolved for repository <directory>: "

  Scenario: No worktree or credentials copy remains after a package reaches a terminal outcome
    Given a router test repository
    And a registered router worktree for package "kbs-hygiene" claim "claim-hygiene"
    And an OpenCode data directory holding a credentials copy for package "kbs-hygiene"
    When the router finishes package "kbs-hygiene" with a terminal outcome
    Then no router worktree should remain registered for package "kbs-hygiene"
    And no OpenCode data directory should remain for package "kbs-hygiene"

  Scenario: Finishing a package leaves the worktree of another package alone
    Given a router test repository
    And a registered router worktree for package "kbs-hygiene" claim "claim-hygiene"
    And a registered router worktree for package "kbs-other" claim "claim-other"
    When the router finishes package "kbs-hygiene" with a terminal outcome
    Then no router worktree should remain registered for package "kbs-hygiene"
    And a router worktree should remain registered for package "kbs-other"

  Scenario: A worktree whose directory vanished is pruned
    Given a router test repository
    And a registered router worktree for package "kbs-hygiene" claim "claim-hygiene"
    And the directory of the router worktree for package "kbs-hygiene" was deleted
    When the router prunes stale worktrees
    Then no router worktree should remain registered for package "kbs-hygiene"

  Scenario Outline: Credentials are redacted from persisted agent output and newlines are preserved
    Given agent output with a <family> credential assembled from "<prefix>" and "<body>" joined by <joiner> between two text lines
    When the agent output is redacted for persistence
    Then the redacted output should have 3 lines
    And the redacted output should not contain "<body>"
    And the redacted output should contain "[REDACTED]"

    Examples:
      | family                | prefix                 | joiner | body                                       |
      | OpenAI                | sk-                    | none   | AbCdEf1234567890xyz                        |
      | OpenAI project        | sk-proj-               | none   | AbCdEf_123456-7890xyz                      |
      | GitHub classic        | ghp_                   | none   | 0123456789abcdefghijABCDEFGHIJ0123         |
      | GitHub OAuth          | gho_                   | none   | 0123456789abcdefghijABCDEFGHIJ0123         |
      | GitHub server         | ghs_                   | none   | 0123456789abcdefghijABCDEFGHIJ0123         |
      | GitHub fine grained   | github_pat_            | none   | 11ABCDEFG0123456789_abcdefghijklmnopqrstuv |
      | AWS access key        | AKIA                   | none   | IOSFODNN7EXAMPLE                           |
      | AWS session key       | ASIA                   | none   | IOSFODNN7EXAMPLE                           |
      | AWS secret key        | aws_secret_access_key= | none   | wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY   |
      | Slack bot             | xoxb-                  | none   | 123456789012-abcdefghijkl                  |
      | Slack user            | xoxp-                  | none   | 123456789012-abcdefghijkl                  |
      | Slack app             | xoxa-                  | none   | 123456789012-abcdefghijkl                  |
      | Slack refresh         | xoxr-                  | none   | 123456789012-abcdefghijkl                  |
      | Authorization header  | Authorization: Bearer  | space  | abc.def-ghi                                |
      | Bearer value          | sent Bearer            | space  | abcdefghijklmnopqrstuvwxyz0123456789       |

  Scenario Outline: The mutex API client refuses plaintext transport for non-loopback hosts
    Given a mutex API client configuration with endpoint "<endpoint>" and a bearer token
    When the mutex API client acquires a lease
    Then the mutex API client error should be <outcome>

    Examples:
      | endpoint                      | outcome                                                                  |
      | http://mutex.example.com      | "mutex api endpoint must use https unless the host is loopback"          |
      | http://10.0.0.5:8080          | "mutex api endpoint must use https unless the host is loopback"          |
      | http://127.0.0.1:9            | "mutex api unavailable"                                                  |
      | http://localhost:9            | "mutex api unavailable"                                                  |
      | http://[::1]:9                | "mutex api unavailable"                                                  |
