# Security

## Code Security
When writing or modifying code, always consider security implications:

### Input Validation
- Validate and sanitize all user inputs at system boundaries
- Never trust data from external sources (APIs, user input, files)
- Use parameterized queries for database operations - NEVER concatenate user input into SQL
- Escape output appropriately for the context (HTML, JavaScript, URLs, etc.)

### Common Vulnerabilities to Avoid
- **Command Injection**: Never pass unsanitized user input to shell commands. Use `shlex.quote()` in Python or equivalent
- **SQL Injection**: Always use parameterized queries or ORM methods, never string concatenation
- **XSS (Cross-Site Scripting)**: Escape all user-provided content before rendering in HTML
- **Path Traversal**: Validate file paths, reject `..` sequences, use allowlists for directories
- **SSRF (Server-Side Request Forgery)**: Validate URLs, use allowlists for external requests
- **Insecure Deserialization**: Avoid `pickle`, `eval()`, `exec()` on untrusted data

### Secrets Management
- NEVER hardcode API keys, passwords, or tokens in source code
- NEVER commit secrets to git (even if you plan to remove them later - they stay in history)
- Use environment variables or secure secret management systems
- If you see secrets in code, warn the user immediately and suggest moving them to environment variables
- Files to never commit: `.env`, `*credentials*`, `*secret*`, `*.pem`, `*.key`, `config.local.*`

### File Operations
- Validate file paths before reading/writing
- Check file permissions before operations
- Never execute files from untrusted sources
- Be cautious with file uploads - validate type, size, and content

## Operational Security
- Never expose internal system information in error messages
- Log security-relevant events but never log sensitive data (passwords, tokens, PII)
- Use HTTPS for all external communications
- Implement rate limiting where appropriate
- Follow the principle of least privilege

## When You Spot Security Issues
If you notice existing security vulnerabilities in the codebase:
1. Warn the user immediately about the risk
2. Explain the potential impact
3. Suggest a fix or mitigation
4. If critical (exposed secrets, active exploitation), prioritize fixing over other tasks
