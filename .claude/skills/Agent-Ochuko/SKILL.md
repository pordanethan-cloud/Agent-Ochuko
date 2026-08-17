```markdown
# Agent-Ochuko Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill introduces the core development patterns and conventions found in the Agent-Ochuko TypeScript codebase. It covers file organization, import/export styles, commit message practices, and testing patterns. By following these guidelines, contributors can ensure code consistency and maintainability throughout the project.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `myAgentLogic.ts`, `userProfileHandler.ts`

### Import Style
- Use **relative imports** for referencing other modules/files.
  - Example:
    ```typescript
    import { fetchData } from './dataFetcher';
    ```

### Export Style
- Mixed usage of **named** and **default exports**.
  - Named export example:
    ```typescript
    export function runAgent() { /* ... */ }
    ```
  - Default export example:
    ```typescript
    export default AgentOchuko;
    ```

### Commit Message Patterns
- Commit messages are **freeform** (no strict prefixing), with an average length of 69 characters.
  - Example:
    ```
    Add support for custom agent configuration in initialization
    ```

## Workflows

### Adding a New Feature
**Trigger:** When implementing a new capability or module  
**Command:** `/add-feature`

1. Create a new file using camelCase naming.
2. Write the feature logic in TypeScript.
3. Use relative imports for dependencies.
4. Export your feature (named or default as appropriate).
5. Write corresponding tests in a `*.test.*` file.
6. Commit changes with a clear, descriptive message.

### Writing and Running Tests
**Trigger:** When validating new or existing code  
**Command:** `/run-tests`

1. Create a test file matching the pattern `*.test.*` (e.g., `agentLogic.test.ts`).
2. Write test cases for your logic.
3. Use the project's test runner (framework unknown; check project docs or package.json).
4. Run the tests and ensure all pass before committing.

### Refactoring Code
**Trigger:** When improving or restructuring existing code  
**Command:** `/refactor`

1. Identify code to refactor.
2. Update file and variable names to follow camelCase.
3. Ensure all imports remain relative.
4. Update exports as needed (named or default).
5. Update or add tests if necessary.
6. Commit with a descriptive message.

## Testing Patterns

- Test files follow the `*.test.*` naming convention (e.g., `userHandler.test.ts`).
- The specific testing framework is not detected; check for usage in project dependencies.
- Place tests alongside or near the modules they cover.
- Example test file structure:
  ```typescript
  // userHandler.test.ts
  import { handleUser } from './userHandler';

  test('should process user data correctly', () => {
    // test implementation
  });
  ```

## Commands
| Command       | Purpose                                         |
|---------------|-------------------------------------------------|
| /add-feature  | Start the workflow for adding a new feature     |
| /run-tests    | Run all tests in the codebase                   |
| /refactor     | Begin the process of refactoring code           |
```
