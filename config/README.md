# OntServe Configuration

This directory contains environment configuration files for OntServe.

## Configuration Files

- `development.env` - Development environment settings
- `production.env` - Production environment settings (template)
- `test.env` - Testing environment settings

## Setup Instructions

### For Development

1. Copy `development.env` to `.env` in the project root (if needed)
2. Update database credentials and other settings
3. Run services:
   ```bash
   python web/app.py              # Web interface (port 5003)
   python servers/mcp_server.py   # MCP server (port 8082)
   ```

### For Production

1. Copy `production.env` to `/opt/ontserve/.env` (or your production path)
2. Update all settings with production values:
   - Set strong `SECRET_KEY`
   - Configure production database URL
   - Set `FLASK_ENV=production`
   - Set `FLASK_DEBUG=0`
3. Deploy using systemd services (see DEPLOYMENT.md)

### For Testing

1. Test environment automatically uses `test.env` settings
2. Run tests:
   ```bash
   pytest
   ```

## Environment Variables

### Core Settings

- `FLASK_ENV` - Environment mode (development/production)
- `FLASK_DEBUG` - Enable debug mode (0/1)
- `ENVIRONMENT` - Environment name (development/production/test)
- `SECRET_KEY` - Flask secret key for sessions (REQUIRED in production)

### Database

- `ONTSERVE_DB_URL` - PostgreSQL connection string
  - Format: `postgresql://user:password@host:port/database`
  - Example: `postgresql://postgres:mypass@localhost:5432/ontserve`

### MCP Server

- `ONTSERVE_MCP_PORT` - MCP server port (default: 8082)
- `ONTSERVE_HOST` - Server host (default: 0.0.0.0)
- `ONTSERVE_DEBUG` - Enable MCP debug logging (true/false)

### Database Configuration

- `ONTSERVE_MAX_CONNECTIONS` - Connection pool size (default: 10)
- `ONTSERVE_QUERY_TIMEOUT` - Query timeout in seconds (default: 30)
- `ONTSERVE_ENABLE_VECTOR_SEARCH` - Enable pgvector search (true/false)

### Web Application

- `ONTSERVE_WEB_PORT` - Web server port (default: 5003)
- `ONTSERVE_WEB_HOST` - Web server host (default: 0.0.0.0)

## Security Notes

### Production Checklist

- [ ] Generate strong `SECRET_KEY` (use `python -c 'import secrets; print(secrets.token_hex(32))'`)
- [ ] Set `FLASK_DEBUG=0`
- [ ] Use strong database password
- [ ] Restrict `ONTSERVE_HOST` if needed (e.g., 127.0.0.1 for local only)
- [ ] Enable HTTPS in production
- [ ] Never commit `.env` files to git (already in .gitignore)

## Migration from Shared Config

Previously, OntServe relied on `../shared/.env` for configuration. This has been replaced with local configuration files for better standalone operation.

If migrating from the old setup:
1. Copy values from `../shared/.env` to `config/development.env`
2. Update any application-specific settings
3. Test that services start correctly
4. Remove dependency on shared configuration

## Troubleshooting

### Services won't start
- Check that `.env` file exists or config files are properly loaded
- Verify database is running and accessible
- Check database credentials are correct

### Database connection errors
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Test connection: `psql -U postgres -d ontserve`
- Check `ONTSERVE_DB_URL` format

### Permission errors
- Ensure config files are readable by the service user
- Check file permissions: `chmod 600 config/*.env`

## Support

For issues or questions:
- See main project README
- Check DEPLOYMENT.md for production setup
- Review application logs
