# Security Policy

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| 1.x.x   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to the maintainers or through GitHub's private security advisory feature.

### Reporting Process

1. **Email**: Send details to [security contact email]
2. **GitHub**: Use the "Security" tab to report privately
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix Development**: Based on severity
- **Disclosure**: Coordinated disclosure after fix

## Security Measures

### Automated Security

- **Dependency Scanning**: Automated with Safety and GitHub Dependabot
- **Code Analysis**: Bandit security linting
- **Pre-commit Hooks**: Security checks on every commit
- **CI/CD Pipeline**: Security scans on every pull request

### Best Practices

- No hardcoded secrets or API keys
- Environment variable configuration
- Input validation with Pydantic
- Secure session management for Tidal API
- Minimal file system permissions

## Vulnerability Disclosure

When we receive security reports:

1. **Acknowledge** receipt within 48 hours
2. **Investigate** and assess the impact
3. **Develop** a fix if confirmed
4. **Coordinate** disclosure timing with reporter
5. **Release** security update
6. **Publish** security advisory

## Security Updates

Security updates are released as:

- **Patch releases** for supported versions
- **Security advisories** on GitHub
- **Changelog entries** marking security fixes

## Contact

For security concerns, contact:

- GitHub Security Advisory (preferred)
- Email: [to be added]
