# Git Deployment Sync Agent - OntServe

Specialized agent for deploying OntServe changes from local development (WSL) to production (DigitalOcean server at ontserve.ontorealm.net).

## Cross-Agent Coordination

**This agent is the SOURCE OF TRUTH for OntServe database sync.**

When ProEthica's `ontserve-sync` agent commits case entities to OntServe locally, it should trigger this agent to sync to production. The workflow is:

1. **ProEthica ontserve-sync**: Commits case to local OntServe (creates TTL file, updates local DB)
2. **This agent**: Syncs local OntServe to production (code + DB + ontologies)

**To invoke from ProEthica context:**
```
Use the git-deployment-sync agent for OntServe to deploy the database and ontology changes to production.
```

**Standard database sync** (local -> production):
```bash
# 1. Dump local
PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve --clean --if-exists --no-owner --no-privileges -f /tmp/ontserve_dev_backup.sql

# 2. Transfer
scp /tmp/ontserve_dev_backup.sql digitalocean:/tmp/

# 3. Backup production
ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS pg_dump -h localhost -U ontserve_user -d ontserve --clean --if-exists --no-owner --no-privileges -f /tmp/ontserve_prod_backup_\$(date +%Y%m%d).sql"

# 4. Restore
ssh digitalocean "sudo -u postgres psql -d ontserve -f /tmp/ontserve_dev_backup.sql"

# 5. Grant permissions (CRITICAL)
ssh digitalocean "sudo -u postgres psql -d ontserve -c 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ontserve_user; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ontserve_user;'"

# 6. Restart services (may require user to run manually if sudo not available)
ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"
```

---

## Agent Purpose

This agent handles:
1. Code synchronization (local -> GitHub -> production)
2. Database backup and restoration (ontserve)
3. Service management (gunicorn, nginx)
4. Ontology file synchronization
5. Verification and rollback procedures

## Production Server Details

**Server**: DigitalOcean droplet (shared with ProEthica)
**Domain**: ontserve.ontorealm.net
**SSH Access**: `ssh digitalocean` (alias) or `ssh chris@209.38.62.85`
**App Location**: `/opt/ontserve`
**Venv Location**: `/opt/ontserve/venv`
**Database**: PostgreSQL (ontserve) - User: `ontserve_user`
**Services** (systemd managed):
- `ontserve-web.service` - gunicorn on port 5003
- `ontserve-mcp.service` - MCP server on port 8082
- nginx (reverse proxy on 80/443)

## Server Directory Structure

```
/opt/
  ontserve/           # OntServe application
    venv/             # Python virtual environment
    ontologies/       # TTL ontology files
    web/              # Flask web application
    servers/          # MCP server
    config/           # Configuration files
  proethica/          # ProEthica application (sibling)
  ontextract/         # OntExtract application (sibling)
```

## Deployment Workflow

### Phase 1: Local Preparation

1. **Verify Local Changes**
   ```bash
   cd /home/chris/onto/OntServe
   git status
   git diff
   ```

2. **Run Tests** (recommended)
   ```bash
   cd /home/chris/onto/OntServe
   source venv-ontserve/bin/activate
   pytest tests/ -v
   ```

3. **Create Database Dump** (if deploying database)
   ```bash
   # Local database is 'ontserve' (not 'ontserve_db')
   PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve \
     --clean --if-exists --no-owner --no-privileges \
     -f /tmp/ontserve_dev_backup.sql
   ```

### Phase 2: Git Operations

1. **Commit and Push** (if changes exist)
   ```bash
   git add .
   git commit -m "Descriptive commit message"
   git push origin development
   ```

2. **Merge to Main** (for production deployment)
   ```bash
   git checkout main
   git merge development
   git push origin main
   git checkout development
   ```

### Phase 3: Production Code Deployment

1. **Pull Latest Code**
   ```bash
   ssh digitalocean "cd /opt/ontserve && git fetch origin && git pull origin main"
   ```

2. **Install Dependencies** (if requirements.txt changed)
   ```bash
   ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && pip install -r requirements.txt"
   ```

3. **Sync Ontology Files** (if ontologies changed)
   ```bash
   rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/
   ```

4. **Sync Config Files** (if config changed)
   ```bash
   rsync -avz /home/chris/onto/OntServe/config/*.yaml digitalocean:/opt/ontserve/config/
   ```

5. **Restart Services** (via systemd)
   ```bash
   # Requires sudo access - if not available, services will auto-restart on code changes
   ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"

   # Alternative if sudo not available (services managed by systemd will auto-recover):
   # ssh digitalocean "pkill -f 'gunicorn.*ontserve' || true"
   # ssh digitalocean "pkill -f 'python.*mcp_server' || true"
   ```

### Phase 4: Database Operations (if deploying database)

**IMPORTANT**: Always create a production backup before restoring.

**Production Database Credentials**:
- Database: `ontserve`
- User: `ontserve_user`
- Password: `$ONTSERVE_PROD_DB_PASS`

1. **Create Production Backup First**
   ```bash
   ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS pg_dump -h localhost -U ontserve_user -d ontserve \
     --clean --if-exists --no-owner --no-privileges \
     -f /tmp/ontserve_production_backup_\$(date +%Y%m%d_%H%M%S).sql"
   ```

2. **Transfer Local Dump to Production**
   ```bash
   scp /tmp/ontserve_dev_backup.sql digitalocean:/tmp/
   ```

3. **Restore Database** (requires postgres superuser)
   ```bash
   ssh digitalocean "sudo -u postgres psql -d ontserve -f /tmp/ontserve_dev_backup.sql"
   ```

4. **Grant Permissions to Application User** (CRITICAL after restore)
   ```bash
   # The restore changes table ownership - must grant permissions back to ontserve_user
   ssh digitalocean "sudo -u postgres psql -d ontserve -c 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ontserve_user; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ontserve_user; GRANT USAGE ON SCHEMA public TO ontserve_user;'"
   ```

   **Note**: Without this step, the application will get "permission denied" errors.

### Phase 5: Ontology Refresh (after database restore)

After restoring the database or syncing ontology files, refresh the entity extraction:

```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/active/refresh_entity_extraction.py proethica-intermediate"
```

For case ontologies:
```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/active/refresh_entity_extraction.py proethica-case-4"
```

### Phase 6: Verification

1. **Check Gunicorn Process**
   ```bash
   ssh digitalocean "ps aux | grep gunicorn | grep ontserve"
   ```

2. **Test Application**
   ```bash
   curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
   # Should return 200

   curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/ontology/proethica-intermediate
   # Should return 200
   ```

3. **Verify Database**
   ```bash
   ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS psql -h localhost -U ontserve_user -d ontserve -c 'SELECT COUNT(*) as ontologies FROM ontologies;'"
   ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS psql -h localhost -U ontserve_user -d ontserve -c 'SELECT COUNT(*) as entities FROM ontology_entities;'"
   ```

4. **Check Error Logs**
   ```bash
   ssh digitalocean "tail -20 /tmp/ontserve.log"
   ```

## Environment Differences

### Development (WSL/Local)
- **Location**: /home/chris/onto/OntServe
- **Venv**: venv-ontserve
- **Database**: `ontserve` (postgres/PASS)
- **Web Port**: 5003
- **MCP Port**: 8082
- **URL**: http://localhost:5003
- **Branch**: development

### Production (DigitalOcean)
- **Location**: /opt/ontserve
- **Venv**: venv
- **Database**: `ontserve` (ontserve_user/$ONTSERVE_PROD_DB_PASS)
- **Port**: 5003 (gunicorn) -> nginx -> 80/443
- **MCP Port**: 8082 (internal only)
- **URL**: https://ontserve.ontorealm.net
- **Branch**: main
- **Services**: ontserve-web.service, ontserve-mcp.service (systemd)

## Quick Reference Commands

### Code-Only Deployment
```bash
# Local
cd /home/chris/onto/OntServe
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# Server - pull and restart via systemd
ssh digitalocean "cd /opt/ontserve && git pull origin main"
ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"

# Verify
curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
```

### Code + Ontologies Deployment
```bash
# Local
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# Sync ontologies
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/

# Pull code and restart
ssh digitalocean "cd /opt/ontserve && git pull origin main"
ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"

# Verify
curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
```

### Full Deployment (Code + Database + Ontologies)
```bash
# 1. Create dump locally (database is 'ontserve')
PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve --clean --if-exists --no-owner --no-privileges -f /tmp/ontserve_dev_backup.sql

# 2. Push code
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# 3. Deploy to server
ssh digitalocean "cd /opt/ontserve && git pull origin main"
scp /tmp/ontserve_dev_backup.sql digitalocean:/tmp/
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/

# 4. Backup production database
ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS pg_dump -h localhost -U ontserve_user -d ontserve --clean --if-exists --no-owner --no-privileges -f /tmp/ontserve_prod_backup_\$(date +%Y%m%d).sql"

# 5. Restore database (requires postgres superuser)
ssh digitalocean "sudo -u postgres psql -d ontserve -f /tmp/ontserve_dev_backup.sql"

# 6. CRITICAL: Grant permissions to application user
ssh digitalocean "sudo -u postgres psql -d ontserve -c 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ontserve_user; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ontserve_user;'"

# 7. Restart services
ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"

# 8. Verify
curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS psql -h localhost -U ontserve_user -d ontserve -c 'SELECT COUNT(*) FROM ontology_entities;'"
```

### Ontology Files Only
```bash
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/active/refresh_entity_extraction.py proethica-intermediate"
```

### Config Files Only
```bash
rsync -avz /home/chris/onto/OntServe/config/*.yaml digitalocean:/opt/ontserve/config/
ssh digitalocean "sudo systemctl restart ontserve-web ontserve-mcp"
```

## Pre-Deployment Checklist

- [ ] All local changes committed
- [ ] Tests passing locally (recommended)
- [ ] Database dump created (if deploying database)
- [ ] main branch up to date with development

## Post-Deployment Verification

- [ ] Services running: `ssh digitalocean "systemctl status ontserve-web ontserve-mcp"`
- [ ] Main site responds: https://ontserve.ontorealm.net/ (HTTP 200)
- [ ] MCP health: `ssh digitalocean "curl -s http://localhost:8082/health"`
- [ ] Ontology detail works: https://ontserve.ontorealm.net/ontology/proethica-intermediate
- [ ] Error logs clean: `ssh digitalocean "journalctl -u ontserve-web -n 20 --no-pager"`
- [ ] Database counts match expected values

## Troubleshooting

### Gunicorn Won't Start
```bash
ssh digitalocean "journalctl -u ontserve-web -n 50 --no-pager"
# Check for Python import errors, missing dependencies
```

### Database Connection Errors
```bash
ssh digitalocean "PGPASSWORD=$ONTSERVE_PROD_DB_PASS psql -h localhost -U ontserve_user -d ontserve -c 'SELECT 1;'"
```

### Permission Denied Errors (after database restore)
If you see "permission denied for table" errors after restoring from a local dump:
```bash
ssh digitalocean "sudo -u postgres psql -d ontserve -c 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ontserve_user; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ontserve_user;'"
```
This happens because the local dump was created by postgres user, and restoring changes table ownership.

### Missing Ontologies
```bash
ssh digitalocean "ls -la /opt/ontserve/ontologies/"
# Compare with local: ls -la /home/chris/onto/OntServe/ontologies/
```

### Entity Extraction Issues
```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/active/refresh_entity_extraction.py proethica-intermediate"
```

### Nginx Issues
```bash
ssh digitalocean "sudo nginx -t"
ssh digitalocean "sudo tail -20 /var/log/nginx/error.log"
```

## Agent Invocation Examples

**Code-only deployment:**
"Deploy the latest OntServe changes to production"

**Code + ontologies deployment:**
"Deploy OntServe with updated ontology files"

**Full deployment (code + database + ontologies):**
"Full OntServe deployment including database"

**Ontologies only:**
"Sync OntServe ontology files to production"

**Verify production:**
"Check the status of OntServe on production"
