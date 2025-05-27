# Security Policy

## Environment Variables

⚠️ **CRITICAL**: Never commit `.env` files containing real API keys to version control.

### Safe Practices

1. **Local Development**: Use `.env` files locally but ensure they're in `.gitignore`
2. **Production**: Use GitHub Secrets and Cloud Run environment variables
3. **Testing**: Use `.env.example` as a template

### Required Secrets

All sensitive configuration should be stored as:
- **GitHub Secrets** for CI/CD
- **Cloud Run Environment Variables** for production
- **Local .env files** for development (never committed)

### Security Checklist

- [ ] `.env` files are in `.gitignore`
- [ ] No hardcoded API keys in source code
- [ ] All secrets use environment variables
- [ ] Production uses GitHub Secrets
- [ ] Service URLs are configurable

## Reporting Security Issues

If you discover a security vulnerability, please report it privately to the repository maintainers. 