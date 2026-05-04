#!/usr/bin/env python3

import os
import sys
import logging
import configparser
import json
import hashlib
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# Timezone Jakarta
TZ_JAKARTA = timezone.utc

def load_config(p_config_file=None):
    """Load configuration from INI file"""
    if p_config_file is None:
        v_script_dir = os.path.dirname(os.path.abspath(__file__))
        v_project_dir = os.path.dirname(v_script_dir)
        p_config_file = os.path.join(v_project_dir, 'config', 'config.ini')
    
    if not os.path.exists(p_config_file):
        raise FileNotFoundError(f"Configuration file not found: {p_config_file}")
    
    v_config = configparser.ConfigParser()
    v_config.read(p_config_file)
    return v_config

def load_table_mapping(p_mapping_file=None):
    """Load table mapping configuration from JSON file"""
    if p_mapping_file is None:
        v_script_dir = os.path.dirname(os.path.abspath(__file__))
        v_project_dir = os.path.dirname(v_script_dir)
        p_mapping_file = os.path.join(v_project_dir, 'config', 'table_mapping.json')
    
    if not os.path.exists(p_mapping_file):
        raise FileNotFoundError(f"Table mapping file not found: {p_mapping_file}")
    
    with open(p_mapping_file, 'r', encoding='utf-8') as v_file:
        v_mapping = json.load(v_file)
    
    return v_mapping

def setup_logging(p_config):
    """Setup logging configuration"""
    v_log_level = p_config.get('logging', 'v_log_level', fallback='INFO')
    v_log_file = p_config.get('logging', 'v_log_file', fallback='sync.log')
    v_log_format = p_config.get('logging', 'v_log_format', 
                               fallback='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    v_max_size = p_config.getint('logging', 'v_log_max_size', fallback=10485760)
    v_backup_count = p_config.getint('logging', 'v_log_backup_count', fallback=5)
    
    # Create log directory if not exists
    v_log_dir = os.path.dirname(v_log_file)
    if v_log_dir and not os.path.exists(v_log_dir):
        os.makedirs(v_log_dir)
    
    # Setup logger
    v_logger = logging.getLogger('db_sync')
    v_logger.setLevel(getattr(logging, v_log_level.upper()))
    
    # Remove existing handlers
    for v_handler in v_logger.handlers[:]:
        v_logger.removeHandler(v_handler)
    
    # File handler with rotation
    v_file_handler = RotatingFileHandler(
        v_log_file, 
        maxBytes=v_max_size, 
        backupCount=v_backup_count
    )
    v_file_handler.setFormatter(logging.Formatter(v_log_format))
    v_logger.addHandler(v_file_handler)
    
    # Console handler
    v_console_handler = logging.StreamHandler(sys.stdout)
    v_console_handler.setFormatter(logging.Formatter(v_log_format))
    v_logger.addHandler(v_console_handler)
    
    return v_logger

def get_jakarta_datetime():
    """Get current datetime in Jakarta timezone"""
    return datetime.now(TZ_JAKARTA).strftime('%Y-%m-%d %H:%M:%S')

def generate_checksum(p_data):
    """Generate SHA256 checksum for data validation"""
    if isinstance(p_data, str):
        v_data_bytes = p_data.encode('utf-8')
    else:
        v_data_bytes = str(p_data).encode('utf-8')
    
    return hashlib.sha256(v_data_bytes).hexdigest()

def format_duration(p_start_time, p_end_time):
    """Format duration between two datetime objects"""
    v_duration = p_end_time - p_start_time
    v_total_seconds = int(v_duration.total_seconds())
    
    v_hours = v_total_seconds // 3600
    v_minutes = (v_total_seconds % 3600) // 60
    v_seconds = v_total_seconds % 60
    
    if v_hours > 0:
        return f"{v_hours}h {v_minutes}m {v_seconds}s"
    elif v_minutes > 0:
        return f"{v_minutes}m {v_seconds}s"
    else:
        return f"{v_seconds}s"

def validate_table_config(p_table_config):
    """Validate table configuration"""
    v_required_fields = [
        'v_table_name', 'v_oracle_table', 'v_postgres_table', 
        'v_sync_mode', 'v_primary_key', 'v_column_mapping'
    ]
    
    for v_field in v_required_fields:
        if v_field not in p_table_config:
            raise ValueError(f"Missing required field in table config: {v_field}")
    
    if p_table_config['v_sync_mode'] == 'incremental':
        if not p_table_config.get('v_timestamp_column'):
            raise ValueError(f"Incremental sync requires v_timestamp_column for table: {p_table_config['v_table_name']}")
    
    return True

def create_checkpoint_file(p_table_name, p_checkpoint_data):
    """Create checkpoint file for sync progress"""
    v_script_dir = os.path.dirname(os.path.abspath(__file__))
    v_project_dir = os.path.dirname(v_script_dir)
    v_checkpoint_dir = os.path.join(v_project_dir, 'data', 'checkpoints')
    
    if not os.path.exists(v_checkpoint_dir):
        os.makedirs(v_checkpoint_dir)
    
    v_checkpoint_file = os.path.join(v_checkpoint_dir, f"{p_table_name}_checkpoint.json")
    
    v_checkpoint_data['v_last_updated'] = get_jakarta_datetime()
    
    with open(v_checkpoint_file, 'w', encoding='utf-8') as v_file:
        json.dump(v_checkpoint_data, v_file, indent=2, default=str)
    
    return v_checkpoint_file

def load_checkpoint_file(p_table_name):
    """Load checkpoint file for sync progress"""
    v_script_dir = os.path.dirname(os.path.abspath(__file__))
    v_project_dir = os.path.dirname(v_script_dir)
    v_checkpoint_file = os.path.join(v_project_dir, 'data', 'checkpoints', f"{p_table_name}_checkpoint.json")
    
    if not os.path.exists(v_checkpoint_file):
        return None
    
    try:
        with open(v_checkpoint_file, 'r', encoding='utf-8') as v_file:
            v_checkpoint_data = json.load(v_file)
        return v_checkpoint_data
    except (json.JSONDecodeError, IOError) as v_error:
        logging.getLogger('db_sync').warning(f"Failed to load checkpoint for {p_table_name}: {v_error}")
        return None

def sanitize_sql_identifier(p_identifier):
    """Sanitize SQL identifier to prevent injection"""
    # Remove dangerous characters and limit length
    v_sanitized = ''.join(c for c in p_identifier if c.isalnum() or c in '_.')
    return v_sanitized[:64]  # Limit to 64 characters

def format_bytes(p_bytes):
    """Format bytes to human readable format"""
    for v_unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if p_bytes < 1024.0:
            return f"{p_bytes:.2f} {v_unit}"
        p_bytes /= 1024.0
    return f"{p_bytes:.2f} PB"

def get_table_row_count_estimate(p_cursor, p_table_name):
    """Get estimated row count for a table"""
    try:
        # For Oracle, use user_tables statistics
        v_sql = """
        SELECT num_rows 
        FROM user_tables 
        WHERE table_name = UPPER(:table_name)
        """
        p_cursor.execute(v_sql, {'table_name': p_table_name.split('.')[-1]})
        v_result = p_cursor.fetchone()
        
        if v_result and v_result[0]:
            return v_result[0]
        else:
            # Fallback to count(*) for small tables
            v_count_sql = f"SELECT COUNT(*) FROM {p_table_name}"
            p_cursor.execute(v_count_sql)
            return p_cursor.fetchone()[0]
            
    except Exception as v_error:
        logging.getLogger('db_sync').warning(f"Failed to get row count for {p_table_name}: {v_error}")
        return 0