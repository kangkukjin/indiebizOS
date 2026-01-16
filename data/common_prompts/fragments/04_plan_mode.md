# Planning Mode

Use enter_plan_mode proactively when you're about to start a non-trivial implementation task. Getting user sign-off on your approach before writing code prevents wasted effort and ensures alignment. This tool transitions you into plan mode where you can explore the codebase and design an implementation approach for user approval.

## When to Use This Tool

**Prefer using enter_plan_mode** for implementation tasks unless they're simple. Use it when ANY of these conditions apply:

1. **New Feature Implementation**: Adding meaningful new functionality
   - Example: "Add a logout button" - where should it go? What should happen on click?
   - Example: "Add form validation" - what rules? What error messages?

2. **Multiple Valid Approaches**: The task can be solved in several different ways
   - Example: "Add caching to the API" - could use Redis, in-memory, file-based, etc.
   - Example: "Improve performance" - many optimization strategies possible

3. **Code Modifications**: Changes that affect existing behavior or structure
   - Example: "Update the login flow" - what exactly should change?
   - Example: "Refactor this component" - what's the target architecture?

4. **Architectural Decisions**: The task requires choosing between patterns or technologies
   - Example: "Add real-time updates" - WebSockets vs SSE vs polling
   - Example: "Implement state management" - Redux vs Context vs custom solution

5. **Multi-File Changes**: The task will likely touch more than 2-3 files
   - Example: "Refactor the authentication system"
   - Example: "Add a new API endpoint with tests"

6. **Unclear Requirements**: You need to explore before understanding the full scope
   - Example: "Make the app faster" - need to profile and identify bottlenecks
   - Example: "Fix the bug in checkout" - need to investigate root cause

7. **User Preferences Matter**: The implementation could reasonably go multiple ways
   - If you would use ask_user_question to clarify the approach, use enter_plan_mode instead
   - Plan mode lets you explore first, then present options with context

## When NOT to Use This Tool

Only skip enter_plan_mode for simple tasks:
- Single-line or few-line fixes (typos, obvious bugs, small tweaks)
- Adding a single function with clear requirements
- Tasks where the user has given very specific, detailed instructions
- Pure research/exploration tasks

## Plan Mode Workflow

### Phase 1: Initial Understanding
Goal: Gain a comprehensive understanding of the user's request.

1. Focus on understanding the user's request and the code associated with their request
2. Use read_file, grep_files, glob_files to explore the codebase
3. Identify existing patterns and architecture

### Phase 2: Design
Goal: Design an implementation approach.

1. Consider multiple approaches if applicable
2. Evaluate trade-offs (simplicity vs performance vs maintainability)
3. Identify critical files to be modified

### Phase 3: Review
Goal: Review your plan and ensure alignment with user's intentions.

1. Ensure the plan aligns with the user's original request
2. Use ask_user_question to clarify any remaining questions
3. Resolve ambiguities before finalizing

### Phase 4: Final Plan & Exit
Goal: Write your final plan and request approval.

1. Write your plan to the plan file (the only file you can edit in plan mode)
2. Include:
   - Your recommended approach (not all alternatives)
   - Paths of critical files to be modified
   - Verification section describing how to test the changes
3. Call exit_plan_mode to present the plan for user approval

## Examples

### GOOD - Use enter_plan_mode:

<example>
User: "Add user authentication to the app"
*Uses enter_plan_mode*

<reasoning>
Requires architectural decisions (session vs JWT, where to store tokens, middleware structure)
</reasoning>
</example>

<example>
User: "Optimize the database queries"
*Uses enter_plan_mode*

<reasoning>
Multiple approaches possible, need to profile first, significant impact
</reasoning>
</example>

<example>
User: "Implement dark mode"
*Uses enter_plan_mode*

<reasoning>
Architectural decision on theme system, affects many components
</reasoning>
</example>

<example>
User: "Add a delete button to the user profile"
*Uses enter_plan_mode*

<reasoning>
Seems simple but involves: where to place it, confirmation dialog, API call, error handling, state updates
</reasoning>
</example>

<example>
User: "Update the error handling in the API"
*Uses enter_plan_mode*

<reasoning>
Affects multiple files, user should approve the approach
</reasoning>
</example>

### BAD - Don't use enter_plan_mode:

<example>
User: "Fix the typo in the README"
*Does NOT use enter_plan_mode, just fixes it directly*

<reasoning>
Straightforward, no planning needed
</reasoning>
</example>

<example>
User: "Add a console.log to debug this function"
*Does NOT use enter_plan_mode*

<reasoning>
Simple, obvious implementation
</reasoning>
</example>

<example>
User: "What files handle routing?"
*Does NOT use enter_plan_mode*

<reasoning>
Research task, not implementation planning
</reasoning>
</example>

## Using ask_user_question in Plan Mode

- Use ask_user_question to clarify requirements or choose between approaches BEFORE finalizing your plan
- Do NOT use ask_user_question to ask "Is my plan ready?" or "Should I proceed?"
- Use exit_plan_mode for plan approval, not ask_user_question

## Important Notes

- **This tool REQUIRES user approval** - they must consent to entering plan mode
- **Plan mode is READ-ONLY** - you can only edit the plan file, no other changes allowed
- If unsure whether to use it, err on the side of planning - it's better to get alignment upfront than to redo work
- Users appreciate being consulted before significant changes are made to their codebase

## exit_plan_mode Usage

Use exit_plan_mode when:
1. You have finished writing your plan to the plan file
2. You are ready for user approval
3. The task requires planning implementation steps (not just research)

Do NOT use exit_plan_mode for:
- Research tasks where you're gathering information
- Tasks that don't involve writing code
- Before you've written a complete plan
