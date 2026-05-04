#!/usr/bin/env python3

import psycopg2
import psycopg2.extras
import logging
import pandas as pd
from datetime import datetime
from .utils import sanitize_sql_identifier

class PostgresConnector:
    """PostgreSQL database connector with bulk operations"""
    
    def __init__(self, p_config):
        self.v_logger = logging.getLogger('db_sync.postgres')
        self.v_config = p_config
        self.v_connection = None
        self.v_cursor = None
        
        # Connection parameters
        self.v_host = p_config.get('postgres_target', 'v_host')
        self.v_port = p_config.getint('postgres_target', 'v_port')
        self.v_database = p_config.get('postgres_target', 'v_database')
        self.v_username = p_config.get('postgres_target', 'v_username')
        self.v_password = p_config.get('postgres_target', 'v_password')
        self.v_schema = p_config.get('postgres_target', 'v_schema', fallback='public')
        
        self.v_logger.info(f"PostgreSQL connector initialized for {self.v_host}:{self.v_port}/{self.v_database}")
    
    def connect(self):
        """Establish connection to PostgreSQL database"""
        try:
            self.v_connection = psycopg2.connect(
                host=self.v_host,
                port=self.v_port,
                database=self.v_database,
                user=self.v_username,
                password=self.v_password
            )
            
            self.v_connection.autocommit = False
            self.v_cursor = self.v_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Set session parameters
            self.v_cursor.execute("SET timezone = 'Asia/Jakarta'")
            self.v_cursor.execute(f"SET search_path TO {self.v_schema}")
            
            self.v_logger.info("Successfully connected to PostgreSQL database")
            return True
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Failed to connect to PostgreSQL: {v_error}")
            return False
    
    def disconnect(self):
        """Close PostgreSQL database connection"""
        try:
            if self.v_cursor:
                self.v_cursor.close()
                self.v_cursor = None
            
            if self.v_connection:
                self.v_connection.close()
                self.v_connection = None
            
            self.v_logger.info("PostgreSQL connection closed")
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error closing PostgreSQL connection: {v_error}")
    
    def test_connection(self):
        """Test PostgreSQL database connection"""
        try:
            if not self.v_connection:
                if not self.connect():
                    return False
            
            self.v_cursor.execute("SELECT 1")
            v_result = self.v_cursor.fetchone()
            
            if v_result and v_result[0] == 1:
                self.v_logger.info("PostgreSQL connection test successful")
                return True
            else:
                self.v_logger.error("PostgreSQL connection test failed")
                return False
                
        except psycopg2.Error as v_error:
            self.v_logger.error(f"PostgreSQL connection test error: {v_error}")
            return False
    
    def create_table_if_not_exists(self, p_table_config):
        """Create PostgreSQL table if it doesn't exist"""
        try:
            v_table_name = sanitize_sql_identifier(p_table_config['v_postgres_table'])
            v_data_types = p_table_config['v_data_types']
            v_primary_key = p_table_config['v_primary_key']
            
            # Build column definitions
            v_columns = []
            for v_postgres_col, v_data_type in v_data_types.items():
                v_column_def = f"{v_postgres_col} {v_data_type}"
                v_columns.append(v_column_def)
            
            v_columns_sql = ",\n    ".join(v_columns)
            
            # Create table SQL
            v_create_sql = f"""
            CREATE TABLE IF NOT EXISTS {v_table_name} (
                {v_columns_sql},
                PRIMARY KEY ({v_primary_key})
            )
            """
            
            self.v_cursor.execute(v_create_sql)
            self.v_connection.commit()
            
            self.v_logger.info(f"Table {v_table_name} created or already exists")
            
            # Create indexes for timestamp columns
            v_timestamp_column = p_table_config.get('v_timestamp_column')
            if v_timestamp_column:
                v_postgres_timestamp_col = None
                for v_oracle_col, v_postgres_col in p_table_config['v_column_mapping'].items():
                    if v_oracle_col == v_timestamp_column:
                        v_postgres_timestamp_col = v_postgres_col
                        break
                
                if v_postgres_timestamp_col:
                    v_index_name = f"idx_{v_table_name.replace('.', '_')}_{v_postgres_timestamp_col}"
                    v_index_sql = f"""
                    CREATE INDEX IF NOT EXISTS {v_index_name} 
                    ON {v_table_name} ({v_postgres_timestamp_col})
                    """
                    self.v_cursor.execute(v_index_sql)
                    self.v_connection.commit()
                    self.v_logger.info(f"Index {v_index_name} created")
            
            return True
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error creating table {p_table_config['v_postgres_table']}: {v_error}")
            self.v_connection.rollback()
            raise
    
    def bulk_insert_data(self, p_table_config, p_dataframe):
        """Bulk insert data into PostgreSQL table"""
        try:
            if p_dataframe.empty:
                self.v_logger.info("No data to insert")
                return 0
            
            v_table_name = sanitize_sql_identifier(p_table_config['v_postgres_table'])
            v_columns = list(p_dataframe.columns)
            v_row_count = len(p_dataframe)
            
            # Convert DataFrame to list of tuples
            v_data_tuples = [tuple(row) for row in p_dataframe.values]
            
            # Build INSERT SQL
            v_columns_sql = ", ".join(v_columns)
            v_placeholders = ", ".join(["%s"] * len(v_columns))
            v_insert_sql = f"INSERT INTO {v_table_name} ({v_columns_sql}) VALUES ({v_placeholders})"
            
            # Execute bulk insert
            psycopg2.extras.execute_batch(
                self.v_cursor,
                v_insert_sql,
                v_data_tuples,
                page_size=1000
            )
            
            self.v_connection.commit()
            self.v_logger.info(f"Successfully inserted {v_row_count} rows into {v_table_name}")
            
            return v_row_count
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error bulk inserting data into {p_table_config['v_postgres_table']}: {v_error}")
            self.v_connection.rollback()
            raise
    
    def upsert_data(self, p_table_config, p_dataframe):
        """Upsert (INSERT ON CONFLICT UPDATE) data into PostgreSQL table"""
        try:
            if p_dataframe.empty:
                self.v_logger.info("No data to upsert")
                return 0
            
            v_table_name = sanitize_sql_identifier(p_table_config['v_postgres_table'])
            v_primary_key = p_table_config['v_primary_key']
            v_columns = list(p_dataframe.columns)
            v_row_count = len(p_dataframe)
            
            # Convert DataFrame to list of tuples
            v_data_tuples = [tuple(row) for row in p_dataframe.values]
            
            # Build UPSERT SQL
            v_columns_sql = ", ".join(v_columns)
            v_placeholders = ", ".join(["%s"] * len(v_columns))
            
            # Build UPDATE clause (exclude primary key)
            v_update_columns = [col for col in v_columns if col != v_primary_key]
            v_update_sql = ", ".join([f"{col} = EXCLUDED.{col}" for col in v_update_columns])
            
            v_upsert_sql = f"""
            INSERT INTO {v_table_name} ({v_columns_sql}) 
            VALUES ({v_placeholders})
            ON CONFLICT ({v_primary_key}) 
            DO UPDATE SET {v_update_sql}
            """
            
            # Execute bulk upsert
            psycopg2.extras.execute_batch(
                self.v_cursor,
                v_upsert_sql,
                v_data_tuples,
                page_size=1000
            )
            
            self.v_connection.commit()
            self.v_logger.info(f"Successfully upserted {v_row_count} rows into {v_table_name}")
            
            return v_row_count
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error upserting data into {p_table_config['v_postgres_table']}: {v_error}")
            self.v_connection.rollback()
            raise
    
    def truncate_table(self, p_table_name):
        """Truncate PostgreSQL table"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            v_truncate_sql = f"TRUNCATE TABLE {v_table_name_clean} RESTART IDENTITY CASCADE"
            
            self.v_cursor.execute(v_truncate_sql)
            self.v_connection.commit()
            
            self.v_logger.info(f"Table {v_table_name_clean} truncated successfully")
            return True
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error truncating table {p_table_name}: {v_error}")
            self.v_connection.rollback()
            raise
    
    def get_table_row_count(self, p_table_name):
        """Get row count from PostgreSQL table"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            v_count_sql = f"SELECT COUNT(*) FROM {v_table_name_clean}"
            
            self.v_cursor.execute(v_count_sql)
            v_count = self.v_cursor.fetchone()[0]
            
            return v_count
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error getting row count from {p_table_name}: {v_error}")
            return 0
    
    def get_max_timestamp(self, p_table_name, p_timestamp_column):
        """Get maximum timestamp value from PostgreSQL table"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            v_timestamp_col_clean = sanitize_sql_identifier(p_timestamp_column)
            
            v_sql = f"""
            SELECT MAX({v_timestamp_col_clean}) 
            FROM {v_table_name_clean}
            """
            
            self.v_cursor.execute(v_sql)
            v_result = self.v_cursor.fetchone()
            
            if v_result and v_result[0]:
                v_max_timestamp = v_result[0]
                if isinstance(v_max_timestamp, datetime):
                    return v_max_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    return str(v_max_timestamp)
            
            return None
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error getting max timestamp from {p_table_name}.{p_timestamp_column}: {v_error}")
            raise
    
    def validate_table_exists(self, p_table_name):
        """Validate if table exists in PostgreSQL"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            
            v_sql = """
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = %s
            """
            
            # Extract schema and table name
            if '.' in v_table_name_clean:
                v_schema, v_table = v_table_name_clean.split('.', 1)
            else:
                v_schema = self.v_schema
                v_table = v_table_name_clean
            
            self.v_cursor.execute(v_sql, (v_schema, v_table))
            v_count = self.v_cursor.fetchone()[0]
            
            v_exists = v_count > 0
            self.v_logger.info(f"PostgreSQL table {v_table_name_clean} exists: {v_exists}")
            
            return v_exists
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error validating PostgreSQL table {p_table_name}: {v_error}")
            return False
    
    def execute_sql(self, p_sql, p_params=None):
        """Execute custom SQL query"""
        try:
            self.v_cursor.execute(p_sql, p_params)
            self.v_connection.commit()
            return True
            
        except psycopg2.Error as v_error:
            self.v_logger.error(f"Error executing SQL: {v_error}")
            self.v_connection.rollback()
            raise
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()