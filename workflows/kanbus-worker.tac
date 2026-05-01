-- Generic Kanbus worker procedure for the experimental Tactus runtime.
--
-- Kanbus injects a host module named "kanbus" with guarded workspace tools.
-- Kanbus still owns validation, commit, push, PR creation, and run records.

local kanbus = require("kanbus")
local done = require("tactus.tools.done")

read_file = Tool {
    description = "Read a repository-relative file from the isolated workspace.",
    input = {
        path = field.string{required = true}
    },
    function(args)
        return kanbus.read_file(args.path)
    end
}

write_file = Tool {
    description = "Write a repository-relative file in the isolated workspace.",
    input = {
        path = field.string{required = true},
        content = field.string{required = true}
    },
    function(args)
        return kanbus.write_file(args.path, args.content)
    end
}

list_files = Tool {
    description = "List repository-relative files in the isolated workspace.",
    input = {
        path = field.string{required = false}
    },
    function(args)
        return kanbus.list_files(args.path or "")
    end
}

run_command = Tool {
    description = "Run a guarded non-publication command inside the isolated workspace.",
    input = {
        command = field.string{required = true},
        timeout_seconds = field.number{required = false}
    },
    function(args)
        return kanbus.run_command(args.command, args.timeout_seconds or 120)
    end
}

comment_on_task = Tool {
    description = "Comment on the assigned Kanbus task only.",
    input = {
        text = field.string{required = true}
    },
    function(args)
        return kanbus.comment(args.text)
    end
}

planner = Agent {
    provider = "openai",
    model = "gpt-4o-mini",
    system_prompt = [[
You plan the assigned Kanbus task. Use the provided issue and repository policy.
Return a concise implementation plan. Do not edit files.
]],
}

implementer = Agent {
    provider = "openai",
    model = "gpt-4o-mini",
    system_prompt = [[
You implement exactly the assigned Kanbus task in the isolated workspace.

Rules:
- Use only the tools provided for this turn.
- Read files before changing them.
- Keep edits scoped to the issue.
- Do not run git add, git commit, git push, gh, or Kanbus mutation commands.
- You may comment only on the assigned Kanbus task.
- When finished, call done with a concise summary.
]],
    tools = {read_file, write_file, list_files, run_command, comment_on_task, done},
}

local function changed_files()
    local result = kanbus.run_command("git status --porcelain --untracked-files=all", 30)
    local files = {}
    if type(result) ~= "table" or result.stdout == nil then
        return files
    end
    for line in string.gmatch(result.stdout, "[^\n]+") do
        local path = string.sub(line, 4)
        if path ~= "" then
            table.insert(files, path)
        end
    end
    return files
end

Procedure {
    input = {
        issue = field.object{required = true},
        repo_policy = field.object{required = true},
        workspace = field.object{required = true},
        run = field.object{required = true},
        prompt = field.string{required = true}
    },
    output = {
        status = field.string{required = true},
        summary = field.string{required = true},
        changed_files = field.array{required = true},
        notes = field.array{required = false}
    },
    function(input)
        local plan_result = planner({
            message = input.prompt,
            context = {
                issue = input.issue,
                repo_policy = input.repo_policy,
                workspace = input.workspace,
                run = input.run
            }
        })

        local plan_text = "Plan was generated."
        if plan_result and plan_result.output then
            plan_text = tostring(plan_result.output)
        end

        local max_turns = 12
        local turn_count = 0
        while not done.called() and turn_count < max_turns do
            turn_count = turn_count + 1
            implementer({
                message = "Implement the assigned Kanbus issue. Plan: " .. plan_text,
                context = {
                    issue = input.issue,
                    repo_policy = input.repo_policy,
                    workspace = input.workspace,
                    run = input.run
                }
            })
        end

        local summary = "Tactus worker completed."
        local status = "completed"
        if done.called() then
            local call = done.last_call()
            if call and call.args and call.args.reason and call.args.reason ~= "" then
                summary = tostring(call.args.reason)
            end
        else
            status = "failed"
            summary = "Tactus worker reached the turn limit before calling done."
        end

        return {
            status = status,
            summary = summary,
            changed_files = changed_files(),
            notes = {
                "Kanbus will run final validation and publication steps."
            }
        }
    end
}
