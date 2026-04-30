---
target:
  branch: develop
  validation: git diff --check
  publish: pull-request
workspace:
  root: ~/.kanbus/orchestration-workspaces
worker:
  branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
codex:
  command: codex app-server
  timeout_seconds: 300
procedures:
  pr_draft:
    runtime: tactus
    timeout_seconds: 120
    source: |
      Procedure {
          input = {
              evidence = field.object{required = true}
          },
          output = {
              title = field.string{required = true},
              body = field.string{required = true}
          },
          function(input)
              local evidence = input.evidence
              local issue = evidence.issue
              local run = evidence.run
              local git = evidence.git

              local title = run.commit_subject or issue.title
              if not string.match(title, "^[a-z]+%(.+%): ") and not string.match(title, "^[a-z]+: ") then
                  title = "chore: " .. string.lower(string.sub(issue.title, 1, 1)) .. string.sub(issue.title, 2)
              end

              local changed_files = {}
              if git.changed_files ~= nil and git.changed_files ~= "" then
                  for line in string.gmatch(git.changed_files, "[^\n]+") do
                      table.insert(changed_files, "- `" .. line .. "`")
                  end
              end
              if #changed_files == 0 then
                  table.insert(changed_files, "- No changed files were reported.")
              end

              local validation_result = run.validation_summary
              if validation_result == nil or validation_result == "" then
                  validation_result = "Completed without output."
              end

              local description = issue.description or "Implements the assigned Kanbus issue."
              if description == "" then
                  description = "Implements the assigned Kanbus issue."
              end

              local body = table.concat({
                  "**Summary**",
                  "- " .. issue.title,
                  table.concat(changed_files, "\n"),
                  "",
                  "**Why**",
                  "- " .. description,
                  "",
                  "**Validation**",
                  "- `" .. run.validation_command .. "`",
                  "- Result: " .. validation_result,
                  "",
                  "**Expected Outcome**",
                  "- The requested change is available on `" .. run.branch .. "` targeting `" .. run.target_branch .. "`.",
                  "",
                  "**Kanbus / Task Tracking**",
                  "- Issue: `" .. issue.id .. "`",
                  "- Run: `" .. run.id .. "`",
                  "- Worker: `" .. run.worker_id .. "`",
                  "- Commit: `" .. (run.commit_sha or "not recorded") .. "`"
              }, "\n")

              return {
                  title = title,
                  body = body
              }
          end
      }
---
You are working in an isolated workspace for the assigned Kanbus issue.

Issue:
- Identifier: {{ issue.identifier }}
- Run: {{ run.id }}
- Title: {{ issue.title }}
- Type: {{ issue.issue_type }}
- Description:
{{ issue.description }}

Rules:
- Use the issue title and description as the source of truth for the task.
- Work only in the isolated workspace supplied by Kanbus orchestration.
- The assigned Kanbus issue is supplied by the orchestrator. Do not create, update, or close Kanbus issues from inside the target workspace.
- You may comment only on the assigned Kanbus issue when useful.
- Do not modify files under project/issues, project/events, or project/runs.
- Do not run git add, git commit, git push, gh pr create, or merge. Kanbus orchestration handles publication after validation.
- Use only non-interactive commands. Do not start shell sessions or commands that require stdin.
- Keep changes scoped to the assigned issue.
- Run the validation that is appropriate for the change before finishing.
