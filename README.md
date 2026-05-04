# Python Database Sync

Sistem sinkronisasi database otomatis dari Oracle ke PostgreSQL menggunakan Python. Dibuat untuk production environment dengan fitur incremental sync, parallel processing, dan monitoring lengkap.

## Fitur

- **Incremental Sync** - Sync hanya data yang berubah berdasarkan timestamp
- **Full Sync** - Sync ulang seluruh table (truncate & reload)
- **Parallel Processing** - Sync multiple tables secara bersamaan
- **Automatic Retry** - Retry otomatis jika ada error
- **Email Notifications** - Laporan hasil sync via email
- **Checkpoint System** - Resume sync dari posisi terakhir
- **Data Validation** - Validasi integritas data
- **Flexible Mapping** - Mapping table dan column yang fleksibel

## Quick Install

```bash
# Clone project
git clone <repository>
cd python-db-sync

# Install sebagai root
sudo python3 install.py
```

Installer akan:
- Install dependencies Python
- Setup direktori di /opt/python-db-sync
- Konfigurasi koneksi database
- Setup cronjob otomatis
- Test konfigurasi

## Manual Setup

### 1. Install Dependencies

```bash
# System packages
sudo apt install python3-pip python3-dev libpq-dev

# Python packages
pip3 install -r requirements.txt
```

### 2. Database Setup

**Oracle Client:**
```bash
# Download Oracle Instant Client
# Set environment variables
export ORACLE_HOME=/opt/oracle/instantclient
export LD_LIBRARY_PATH=$ORACLE_HOME:$LD_LIBRARY_PATH
```

**PostgreSQL:**
```bash
sudo apt install postgresql-client
```

### 3. Configuration

Edit `config/config.ini`:
```ini
[oracle_source]
v_host=oracle-server.com
v_port=1521
v_service_name=PROD
v_username=sync_user
v_password=your_password

[postgres_target]
v_host=postgres-server.com
v_port=5432
v_database=target_db
v_username=sync_user
v_password=your_password
```

Edit `config/table_mapping.json` untuk mapping tables.

## Usage

### Command Line

```bash
# Validate konfigurasi
python3 src/sync_manager.py --mode validate

# Incremental sync (default)
python3 src/sync_manager.py --mode incremental

# Full sync
python3 src/sync_manager.py --mode full

# Sync specific tables
python3 src/sync_manager.py --tables employees_sync orders_sync

# Custom config file
python3 src/sync_manager.py --config /path/to/config.ini --mapping /path/to/mapping.json
```

### Cronjob Setup

```bash
# Incremental sync setiap 30 menit
*/30 * * * * /usr/bin/python3 /opt/python-db-sync/src/sync_manager.py --mode incremental

# Full sync mingguan
0 2 * * 0 /usr/bin/python3 /opt/python-db-sync/src/sync_manager.py --mode full
```

## Table Mapping Configuration

```json
{
  "sync_tables": [
    {
      "v_table_name": "employees_sync",
      "v_oracle_table": "HR.EMPLOYEES", 
      "v_postgres_table": "public.employees",
      "v_sync_mode": "incremental",
      "v_timestamp_column": "LAST_UPDATED",
      "v_primary_key": "EMPLOYEE_ID",
      "v_enabled": true,
      "v_column_mapping": {
        "EMPLOYEE_ID": "employee_id",
        "FIRST_NAME": "first_name",
        "LAST_NAME": "last_name",
        "EMAIL": "email",
        "LAST_UPDATED": "last_updated"
      },
      "v_data_types": {
        "employee_id": "INTEGER",
        "first_name": "VARCHAR(50)",
        "last_name": "VARCHAR(50)",
        "email": "VARCHAR(100)",
        "last_updated": "TIMESTAMP"
      }
    }
  ]
}
```

## Sync Modes

### Incremental Sync
- Sync berdasarkan timestamp column
- Hanya data yang berubah sejak sync terakhir
- Menggunakan UPSERT (INSERT ON CONFLICT UPDATE)
- Cocok untuk sync frequent (setiap 15-30 menit)

### Full Sync
- Truncate table PostgreSQL
- Copy semua data dari Oracle
- Cocok untuk sync weekly/monthly
- Untuk table yang tidak punya timestamp

## Monitoring & Logging

### Log Files
```bash
# Main log
tail -f /opt/python-db-sync/logs/sync.log

# Cron log
tail -f /opt/python-db-sync/logs/cron.log
```

### Email Reports
- Success/Error notifications
- Detailed sync statistics
- HTML formatted reports
- Configurable recipients

### Checkpoints
```bash
# Checkpoint files
ls /opt/python-db-sync/data/checkpoints/

# View checkpoint
cat /opt/python-db-sync/data/checkpoints/employees_sync_checkpoint.json
```

## Performance Tuning

### Batch Size
```ini
[sync_settings]
v_batch_size=5000  # Increase for better performance
```

### Parallel Processing
```ini
v_parallel_workers=8  # Increase based on CPU cores
```

### Oracle Optimization
```sql
-- Update table statistics
EXEC DBMS_STATS.GATHER_TABLE_STATS('HR', 'EMPLOYEES');

-- Add index on timestamp column
CREATE INDEX idx_employees_updated ON HR.EMPLOYEES(LAST_UPDATED);
```

### PostgreSQL Optimization
```sql
-- Increase work_mem for bulk operations
SET work_mem = '256MB';

-- Disable autovacuum during sync
ALTER TABLE employees SET (autovacuum_enabled = false);
```

## Troubleshooting

### Connection Issues
```bash
# Test Oracle connection
sqlplus sync_user/password@oracle-server:1521/PROD

# Test PostgreSQL connection
psql -h postgres-server -U sync_user -d target_db
```

### Sync Errors
```bash
# Check logs
grep ERROR /opt/python-db-sync/logs/sync.log

# Validate configuration
python3 src/sync_manager.py --mode validate

# Test single table
python3 src/sync_manager.py --tables employees_sync
```

### Performance Issues
- Increase batch_size untuk table besar
- Add database indexes
- Use parallel processing
- Schedule sync di off-peak hours

## Security

### Database Permissions
```sql
-- Oracle: Grant minimal permissions
GRANT SELECT ON HR.EMPLOYEES TO sync_user;

-- PostgreSQL: Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON public.employees TO sync_user;
```

### Credential Management
- Gunakan database-specific users
- Rotate passwords regularly
- Use connection pooling
- Monitor access logs

## Tech Stack

- **Python 3.7+** - Main language
- **cx_Oracle** - Oracle database connector
- **psycopg2** - PostgreSQL connector  
- **pandas** - Data manipulation
- **configparser** - Configuration management
- **smtplib** - Email notifications
- **threading** - Parallel processing