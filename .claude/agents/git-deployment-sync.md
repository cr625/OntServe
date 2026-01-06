# Git Deployment Sync Agent - OntServe

Specialized agent for deploying OntServe changes from local development (WSL) to production (DigitalOcean server at ontserve.ontorealm.net).

## Agent Purpose

This agent handles:
1. Code synchronization (local -> GitHub -> production)
2. Database backup and restoration (ontserve_db)
3. Service management (gunicorn, nginx)
4. Ontology file synchronization
5. Verification and rollback procedures

## Production Server Details

**Server**: DigitalOcean droplet (shared with ProEthica)
**Domain**: ontserve.ontorealm.net
**SSH Access**: `ssh digitalocean` (alias) or `ssh chris@209.38.62.85`
**App Location**: `/opt/ontserve`
**Venv Location**: `/opt/ontserve/venv`
**Database**: PostgreSQL (ontserve_db)
**Services**:
- OntServe runs via gunicorn (port 5003)
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
   PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve_db \
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

5. **Restart Gunicorn**
   ```bash
   ssh digitalocean "pkill -f 'gunicorn.*ontserve' || true"
   ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && nohup gunicorn -w 2 -b 127.0.0.1:5003 --timeout 120 --access-logfile - --error-logfile - 'web.app:create_app()' > /tmp/ontserve.log 2>&1 &"
   ```

### Phase 4: Database Operations (if deploying database)

**IMPORTANT**: Always create a production backup before restoring.

1. **Create Production Backup First**
   ```bash
   ssh digitalocean "PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve_db \
     --clean --if-exists --no-owner --no-privileges \
     -f /tmp/ontserve_production_backup_\$(date +%Y%m%d_%H%M%S).sql"
   ```

2. **Transfer Local Dump to Production**
   ```bash
   scp /tmp/ontserve_dev_backup.sql digitalocean:/tmp/
   ```

3. **Restore Database**
   ```bash
   ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -c 'DROP DATABASE IF EXISTS ontserve_db;'"
   ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -c 'CREATE DATABASE ontserve_db;'"
   ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -d ontserve_db -f /tmp/ontserve_dev_backup.sql"
   ```

### Phase 5: Ontology Refresh (after database restore)

After restoring the database or syncing ontology files, refresh the entity extraction:

```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/refresh_entity_extraction.py proethica-intermediate"
```

For case ontologies:
```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/refresh_entity_extraction.py proethica-case-4"
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
   ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -d ontserve_db -c 'SELECT COUNT(*) as ontologies FROM ontologies;'"
   ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -d ontserve_db -c 'SELECT COUNT(*) as entities FROM ontology_entities;'"
   ```

4. **Check Error Logs**
   ```bash
   ssh digitalocean "tail -20 /tmp/ontserve.log"
   ```

## Environment Differences

### Development (WSL/Local)
- **Location**: /home/chris/onto/OntServe
- **Venv**: venv-ontserve
- **Database**: ontserve_db (postgres/PASS)
- **Web Port**: 5003
- **MCP Port**: 8082
- **URL**: http://localhost:5003
- **Branch**: development

### Production (DigitalOcean)
- **Location**: /opt/ontserve
- **Venv**: venv
- **Database**: ontserve_db (postgres/PASS)
- **Port**: 5003 (gunicorn) -> nginx -> 80/443
- **URL**: https://ontserve.ontorealm.net
- **Branch**: main

## Quick Reference Commands

### Code-Only Deployment
```bash
# Local
cd /home/chris/onto/OntServe
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# Server
ssh digitalocean "cd /opt/ontserve && git pull origin main && pkill -f 'gunicorn.*ontserve'"
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && nohup gunicorn -w 2 -b 127.0.0.1:5003 --timeout 120 'web.app:create_app()' > /tmp/ontserve.log 2>&1 &"
```

### Code + Ontologies Deployment
```bash
# Local
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# Sync ontologies
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/

# Restart
ssh digitalocean "cd /opt/ontserve && git pull origin main && pkill -f 'gunicorn.*ontserve'"
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && nohup gunicorn -w 2 -b 127.0.0.1:5003 --timeout 120 'web.app:create_app()' > /tmp/ontserve.log 2>&1 &"

# Verify
curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
```

### Full Deployment (Code + Database + Ontologies)
```bash
# 1. Create dumps locally
PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve_db --clean --if-exists --no-owner -f /tmp/ontserve_dev_backup.sql

# 2. Push code
git push origin development
git checkout main && git merge development && git push origin main && git checkout development

# 3. Deploy to server
ssh digitalocean "cd /opt/ontserve && git pull origin main"
scp /tmp/ontserve_dev_backup.sql digitalocean:/tmp/
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/

# 4. Backup and restore database
ssh digitalocean "PGPASSWORD=PASS pg_dump -h localhost -U postgres -d ontserve_db -f /tmp/ontserve_prod_backup_\$(date +%Y%m%d).sql"
ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -c 'DROP DATABASE IF EXISTS ontserve_db; CREATE DATABASE ontserve_db;'"
ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -d ontserve_db -f /tmp/ontserve_dev_backup.sql"

# 5. Restart service
ssh digitalocean "pkill -f 'gunicorn.*ontserve' || true"
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && nohup gunicorn -w 2 -b 127.0.0.1:5003 --timeout 120 'web.app:create_app()' > /tmp/ontserve.log 2>&1 &"

# 6. Verify
curl -s -o /dev/null -w '%{http_code}' https://ontserve.ontorealm.net/
```

### Ontology Files Only
```bash
rsync -avz --delete /home/chris/onto/OntServe/ontologies/ digitalocean:/opt/ontserve/ontologies/
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/refresh_entity_extraction.py proethica-intermediate"
```

### Config Files Only
```bash
rsync -avz /home/chris/onto/OntServe/config/*.yaml digitalocean:/opt/ontserve/config/
ssh digitalocean "pkill -f 'gunicorn.*ontserve' || true"
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && nohup gunicorn -w 2 -b 127.0.0.1:5003 --timeout 120 'web.app:create_app()' > /tmp/ontserve.log 2>&1 &"
```

## Pre-Deployment Checklist

- [ ] All local changes committed
- [ ] Tests passing locally (recommended)
- [ ] Database dump created (if deploying database)
- [ ] main branch up to date with development

## Post-Deployment Verification

- [ ] Gunicorn running: `ps aux | grep gunicorn | grep ontserve`
- [ ] Main site responds: https://ontserve.ontorealm.net/ (HTTP 200)
- [ ] Ontology detail works: https://ontserve.ontorealm.net/ontology/proethica-intermediate
- [ ] Error logs clean: `tail /tmp/ontserve.log`
- [ ] Database counts match expected values

## Troubleshooting

### Gunicorn Won't Start
```bash
ssh digitalocean "tail -50 /tmp/ontserve.log"
# Check for Python import errors, missing dependencies
```

### Database Connection Errors
```bash
ssh digitalocean "PGPASSWORD=PASS psql -h localhost -U postgres -d ontserve_db -c 'SELECT 1;'"
```

### Missing Ontologies
```bash
ssh digitalocean "ls -la /opt/ontserve/ontologies/"
# Compare with local: ls -la /home/chris/onto/OntServe/ontologies/
```

### Entity Extraction Issues
```bash
ssh digitalocean "cd /opt/ontserve && source venv/bin/activate && python scripts/refresh_entity_extraction.py proethica-intermediate"
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
