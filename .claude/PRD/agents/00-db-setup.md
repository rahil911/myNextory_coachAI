# Phase 0: Database Setup

## Purpose

Install MariaDB on the India machine (Ubuntu/WSL2), load the 205MB MySQL dump, and configure passwordless unix socket authentication so all agents can query `mysql baap -e "..."` without credentials.

## Phase Info

- **Phase**: 0 (sequential, blocks ALL other phases)
- **Estimated time**: 15-30 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `~/Projects/baap/app-mynextory-backup.sql` (205MB MySQL dump)
- **Environment**: Ubuntu on WSL2, user `rahil`, sudo available

## Output Contract

- **Database**: `baap` in MariaDB, all tables loaded
- **Authentication**: Unix socket (passwordless for local user)
- **Flag file**: `~/Projects/baap/db_ready.flag` (touch this when done)

## Step-by-Step Instructions

### 1. Install MariaDB

```bash
# Check if already installed
which mariadb || which mysql

# If not installed:
sudo apt update
sudo apt install -y mariadb-server mariadb-client

# Start the service
sudo service mariadb start

# Verify it's running
sudo service mariadb status
```

### 2. Configure Passwordless Authentication

MariaDB on Ubuntu defaults to unix_socket auth for root. We need the `rahil` user to also authenticate via unix socket.

```bash
# Connect as root
sudo mariadb -e "
  CREATE USER IF NOT EXISTS 'rahil'@'localhost' IDENTIFIED VIA unix_socket;
  GRANT ALL PRIVILEGES ON *.* TO 'rahil'@'localhost' WITH GRANT OPTION;
  FLUSH PRIVILEGES;
"

# Test passwordless access
mysql -e "SELECT 'passwordless auth works' AS status"
```

### 3. Create Database and Load Dump

```bash
# Create the database
mysql -e "CREATE DATABASE IF NOT EXISTS baap CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

# Load the dump (may take several minutes for 205MB)
mysql baap < ~/Projects/baap/app-mynextory-backup.sql

# If you get "ERROR 1118: Row size too large" or similar, try:
# mysql -e "SET GLOBAL innodb_strict_mode=0" && mysql baap < ~/Projects/baap/app-mynextory-backup.sql
```

### 4. Verify the Load

```bash
# Count tables
mysql baap -e "SHOW TABLES" | wc -l

# Check a few key tables
mysql baap -e "SELECT COUNT(*) AS row_count FROM information_schema.tables WHERE table_schema='baap'"

# Sample some data
mysql baap -e "SHOW TABLES" | head -20
```

### 5. Configure Auto-Start

Ensure MariaDB starts when WSL boots:

```bash
# Check if already in wsl.conf
grep -q mariadb /etc/wsl.conf 2>/dev/null || {
  # Add to boot command
  if grep -q '\[boot\]' /etc/wsl.conf 2>/dev/null; then
    # Append to existing boot section
    sudo sed -i '/\[boot\]/a command=service mariadb start' /etc/wsl.conf
  else
    echo -e '\n[boot]\ncommand=service mariadb start' | sudo tee -a /etc/wsl.conf
  fi
}
```

**Note**: If `/etc/wsl.conf` already has a `command=` under `[boot]`, chain it:
```bash
# e.g., command=service ssh start; service mariadb start
```

### 6. Create .gitignore

```bash
cat > ~/Projects/baap/.gitignore << 'EOF'
# Database dump (loaded into MariaDB, no need to track)
app-mynextory-backup.sql

# Python
.venv/
__pycache__/
*.pyc

# IDE
.idea/
.vscode/

# OS
.DS_Store
Thumbs.db

# Agent worktrees
agents/

# Temporary
*.flag
*.tmp
EOF
```

### 7. Initialize Git Repo

```bash
cd ~/Projects/baap
git init
git add .gitignore
git commit -m "Initial commit: .gitignore for baap project"
```

### 8. Create Flag File

```bash
touch ~/Projects/baap/db_ready.flag
```

## Success Criteria

1. `mysql baap -e "SHOW TABLES" | wc -l` returns **100+** (or the actual table count from the dump)
2. `mysql -e "SELECT 'works' AS status"` succeeds without password prompt
3. `~/Projects/baap/db_ready.flag` exists
4. `.gitignore` exists and ignores the SQL dump
5. Git repo initialized with initial commit

## Edge Cases

- If MariaDB is already installed, skip installation
- If the dump has MyISAM tables, they'll work fine (MariaDB supports both)
- If the dump uses `CREATE DATABASE`, it may try to create a different DB name — check and adjust
- If there are character set issues, use `--default-character-set=utf8mb4`
- The dump might contain `DEFINER` clauses — these can be ignored or stripped if they cause errors:
  ```bash
  sed -i 's/DEFINER=[^ ]* //g' ~/Projects/baap/app-mynextory-backup.sql
  ```

## Gotchas

- **WSL networking**: MariaDB binds to `127.0.0.1` by default. This is fine — all access is local.
- **Memory**: The dump is 205MB but the loaded database may be larger. India has 120GB RAM allocated to WSL, so this is not a concern.
- **Existing MariaDB**: If MariaDB is already running with existing databases, DO NOT touch them. Just create the `baap` database.
