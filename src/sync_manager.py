#!/usr/bin/env python3

import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Add src directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import (
    load_config, load_table_mapping, setup_logging, 
    validate_table_config, create_checkpoint_file, 
    load_checkpoint_file, format_duration, get_jakarta_datetime
)
from oracle_connector import OracleConnector
from postgres_connector import PostgresConnector
from notification_sender import NotificationSender

class SyncManager:
    """Main synchronization manager for Oracle to PostgreSQL sync"""
    
    def __init__(self, p_config_file=None, p_mapping_file=None):
        # Load configuration
        self.v_config = load_config(p_config_file)
        self.v_table_mapping = load_table_mapping(p_mapping_file)
        
        # Setup logging
        self.v_logger = setup_logging(self.v_config)
        
        # Initialize components
        self.v_oracle_connector = OracleConnector(self.v_config)
        self.v_postgres_connector = PostgresConnector(self.v_config)
        self.v_notification_sender = NotificationSender(self.v_config)
        
        # Sync settings
        self.v_batch_size = self.v_config.getint('sync_settings', 'v_batch_size', fallback=1000)
        self.v_max_retries = self.v_config.getint('sync_settings', 'v_max_retries', fallback=3)
        self.v_retry_delay = self.v_config.getint('sync_settings', 'v_retry_delay', fallback=5)
        self.v_parallel_workers = self.v_config.getint('sync_settings', 'v_parallel_workers', fallback=4)
        self.v_checkpoint_enabled = self.v_config.getboolean('sync_settings', 'v_checkpoint_enabled', fallback=True)
        
        self.v_logger.info("SyncManager initialized successfully")
    
    def sync_all_tables(self, p_sync_mode='incremental', p_table_names=None):
        """Sync all configured tables"""
        v_start_time = datetime.now()
        self.v_logger.info(f"Starting {p_sync_mode} sync for all tables")
        
        # Get enabled tables
        v_tables_to_sync = []
        for v_table_config in self.v_table_mapping['sync_tables']:
            if not v_table_config.get('v_enabled', True):
                continue
            
            if p_table_names and v_table_config['v_table_name'] not in p_table_names:
                continue
            
            # Validate table configuration
            try:
                validate_table_config(v_table_config)
                v_tables_to_sync.append(v_table_config)
            except ValueError as v_error:
                self.v_logger.error(f"Invalid table configuration for {v_table_config.get('v_table_name', 'Unknown')}: {v_error}")
        
        if not v_tables_to_sync:
            self.v_logger.warning("No tables to sync")
            return []
        
        self.v_logger.info(f"Found {len(v_tables_to_sync)} tables to sync")
        
        # Test connections
        if not self._test_connections():
            self.v_logger.error("Connection test failed, aborting sync")
            return []
        
        # Sync tables (parallel or sequential based on config)
        v_sync_results = []
        
        if self.v_parallel_workers > 1 and len(v_tables_to_sync) > 1:
            v_sync_results = self._sync_tables_parallel(v_tables_to_sync, p_sync_mode)
        else:
            v_sync_results = self._sync_tables_sequential(v_tables_to_sync, p_sync_mode)
        
        # Calculate total statistics
        v_end_time = datetime.now()
        v_total_duration = format_duration(v_start_time, v_end_time)
        v_total_rows = sum(result.get('v_rows_processed', 0) for result in v_sync_results)
        v_success_count = sum(1 for result in v_sync_results if result.get('v_success', True))
        
        self.v_logger.info(f"Sync completed: {v_success_count}/{len(v_sync_results)} tables successful, {v_total_rows:,} rows processed in {v_total_duration}")
        
        # Send notification
        try:
            self.v_notification_sender.send_sync_report(v_sync_results, p_sync_mode)
        except Exception as v_error:
            self.v_logger.error(f"Failed to send notification: {v_error}")
        
        return v_sync_results
    
    def sync_single_table(self, p_table_config, p_sync_mode='incremental'):
        """Sync a single table"""
        v_table_name = p_table_config['v_table_name']
        v_start_time = datetime.now()
        
        self.v_logger.info(f"Starting {p_sync_mode} sync for table: {v_table_name}")
        
        v_sync_result = {
            'v_table_name': v_table_name,
            'v_sync_mode': p_sync_mode,
            'v_start_time': v_start_time,
            'v_success': False,
            'v_rows_processed': 0,
            'v_error_message': None
        }
        
        try:
            # Connect to databases
            with self.v_oracle_connector as v_oracle, self.v_postgres_connector as v_postgres:
                
                # Validate source table exists
                if not v_oracle.validate_table_exists(p_table_config['v_oracle_table']):
                    raise Exception(f"Source table does not exist: {p_table_config['v_oracle_table']}")
                
                # Create target table if not exists
                v_postgres.create_table_if_not_exists(p_table_config)
                
                # Determine sync strategy
                if p_sync_mode == 'full' or p_table_config['v_sync_mode'] == 'full':
                    v_rows_processed = self._perform_full_sync(v_oracle, v_postgres, p_table_config)
                else:
                    v_rows_processed = self._perform_incremental_sync(v_oracle, v_postgres, p_table_config)
                
                v_sync_result['v_rows_processed'] = v_rows_processed
                v_sync_result['v_success'] = True
                
                # Update checkpoint
                if self.v_checkpoint_enabled:
                    self._update_checkpoint(p_table_config, v_oracle)
                
                v_end_time = datetime.now()
                v_duration = (v_end_time - v_start_time).total_seconds()
                v_sync_result['v_end_time'] = v_end_time
                v_sync_result['v_duration_seconds'] = v_duration
                
                self.v_logger.info(f"Successfully synced {v_table_name}: {v_rows_processed:,} rows in {v_duration:.2f}s")
        
        except Exception as v_error:
            v_end_time = datetime.now()
            v_duration = (v_end_time - v_start_time).total_seconds()
            
            v_sync_result['v_end_time'] = v_end_time
            v_sync_result['v_duration_seconds'] = v_duration
            v_sync_result['v_error_message'] = str(v_error)
            
            self.v_logger.error(f"Failed to sync {v_table_name}: {v_error}")
            
            # Send immediate error alert
            try:
                self.v_notification_sender.send_error_alert(str(v_error), v_table_name)
            except Exception as v_notification_error:
                self.v_logger.error(f"Failed to send error notification: {v_notification_error}")
        
        return v_sync_result
    
    def _perform_full_sync(self, p_oracle, p_postgres, p_table_config):
        """Perform full table sync (truncate and reload)"""
        v_table_name = p_table_config['v_table_name']
        self.v_logger.info(f"Performing full sync for {v_table_name}")
        
        # Get all data from Oracle
        v_oracle_data = p_oracle.get_table_data(p_table_config)
        
        if v_oracle_data.empty:
            self.v_logger.info(f"No data found in Oracle table {p_table_config['v_oracle_table']}")
            return 0
        
        # Truncate PostgreSQL table
        p_postgres.truncate_table(p_table_config['v_postgres_table'])
        
        # Insert data in batches
        v_total_rows = len(v_oracle_data)
        v_processed_rows = 0
        
        for v_start_idx in range(0, v_total_rows, self.v_batch_size):
            v_end_idx = min(v_start_idx + self.v_batch_size, v_total_rows)
            v_batch_data = v_oracle_data.iloc[v_start_idx:v_end_idx]
            
            v_batch_rows = p_postgres.bulk_insert_data(p_table_config, v_batch_data)
            v_processed_rows += v_batch_rows
            
            self.v_logger.info(f"Processed batch {v_start_idx + 1}-{v_end_idx} ({v_processed_rows:,}/{v_total_rows:,} rows)")
        
        return v_processed_rows
    
    def _perform_incremental_sync(self, p_oracle, p_postgres, p_table_config):
        """Perform incremental sync based on timestamp"""
        v_table_name = p_table_config['v_table_name']
        v_timestamp_column = p_table_config['v_timestamp_column']
        
        self.v_logger.info(f"Performing incremental sync for {v_table_name}")
        
        # Get last sync timestamp
        v_last_sync_time = None
        
        if self.v_checkpoint_enabled:
            v_checkpoint = load_checkpoint_file(v_table_name)
            if v_checkpoint:
                v_last_sync_time = v_checkpoint.get('v_last_sync_timestamp')
        
        # Fallback: get max timestamp from PostgreSQL
        if not v_last_sync_time:
            try:
                v_postgres_timestamp_col = None
                for v_oracle_col, v_postgres_col in p_table_config['v_column_mapping'].items():
                    if v_oracle_col == v_timestamp_column:
                        v_postgres_timestamp_col = v_postgres_col
                        break
                
                if v_postgres_timestamp_col:
                    v_last_sync_time = p_postgres.get_max_timestamp(
                        p_table_config['v_postgres_table'], 
                        v_postgres_timestamp_col
                    )
            except Exception as v_error:
                self.v_logger.warning(f"Could not get last sync timestamp from PostgreSQL: {v_error}")
        
        # Add lookback buffer for incremental sync
        if v_last_sync_time:
            v_lookback_hours = self.v_table_mapping['sync_rules'].get('v_incremental_lookback_hours', 1)
            v_last_sync_dt = datetime.strptime(v_last_sync_time, '%Y-%m-%d %H:%M:%S')
            v_buffered_sync_dt = v_last_sync_dt - timedelta(hours=v_lookback_hours)
            v_last_sync_time = v_buffered_sync_dt.strftime('%Y-%m-%d %H:%M:%S')
            
            self.v_logger.info(f"Using last sync time with {v_lookback_hours}h buffer: {v_last_sync_time}")
        else:
            self.v_logger.info("No previous sync timestamp found, performing initial sync")
        
        # Get incremental data from Oracle
        v_oracle_data = p_oracle.get_table_data(p_table_config, v_last_sync_time)
        
        if v_oracle_data.empty:
            self.v_logger.info(f"No new data found for {v_table_name}")
            return 0
        
        # Upsert data to PostgreSQL
        v_total_rows = len(v_oracle_data)
        v_processed_rows = 0
        
        for v_start_idx in range(0, v_total_rows, self.v_batch_size):
            v_end_idx = min(v_start_idx + self.v_batch_size, v_total_rows)
            v_batch_data = v_oracle_data.iloc[v_start_idx:v_end_idx]
            
            v_batch_rows = p_postgres.upsert_data(p_table_config, v_batch_data)
            v_processed_rows += v_batch_rows
            
            self.v_logger.info(f"Processed batch {v_start_idx + 1}-{v_end_idx} ({v_processed_rows:,}/{v_total_rows:,} rows)")
        
        return v_processed_rows
    
    def _update_checkpoint(self, p_table_config, p_oracle):
        """Update sync checkpoint"""
        try:
            v_table_name = p_table_config['v_table_name']
            v_timestamp_column = p_table_config.get('v_timestamp_column')
            
            v_checkpoint_data = {
                'v_table_name': v_table_name,
                'v_last_sync_timestamp': None,
                'v_sync_mode': p_table_config['v_sync_mode']
            }
            
            if v_timestamp_column:
                v_max_timestamp = p_oracle.get_max_timestamp(
                    p_table_config['v_oracle_table'], 
                    v_timestamp_column
                )
                v_checkpoint_data['v_last_sync_timestamp'] = v_max_timestamp
            
            create_checkpoint_file(v_table_name, v_checkpoint_data)
            self.v_logger.info(f"Checkpoint updated for {v_table_name}")
            
        except Exception as v_error:
            self.v_logger.warning(f"Failed to update checkpoint for {p_table_config['v_table_name']}: {v_error}")
    
    def _sync_tables_sequential(self, p_tables, p_sync_mode):
        """Sync tables sequentially"""
        v_results = []
        
        for v_table_config in p_tables:
            v_result = self.sync_single_table(v_table_config, p_sync_mode)
            v_results.append(v_result)
        
        return v_results
    
    def _sync_tables_parallel(self, p_tables, p_sync_mode):
        """Sync tables in parallel"""
        v_results = []
        
        with ThreadPoolExecutor(max_workers=self.v_parallel_workers) as v_executor:
            # Submit all sync tasks
            v_future_to_table = {
                v_executor.submit(self.sync_single_table, v_table_config, p_sync_mode): v_table_config
                for v_table_config in p_tables
            }
            
            # Collect results as they complete
            for v_future in as_completed(v_future_to_table):
                v_table_config = v_future_to_table[v_future]
                try:
                    v_result = v_future.result()
                    v_results.append(v_result)
                except Exception as v_error:
                    self.v_logger.error(f"Parallel sync failed for {v_table_config['v_table_name']}: {v_error}")
                    v_results.append({
                        'v_table_name': v_table_config['v_table_name'],
                        'v_sync_mode': p_sync_mode,
                        'v_success': False,
                        'v_rows_processed': 0,
                        'v_error_message': str(v_error)
                    })
        
        return v_results
    
    def _test_connections(self):
        """Test database connections"""
        self.v_logger.info("Testing database connections...")
        
        # Test Oracle connection
        if not self.v_oracle_connector.test_connection():
            self.v_logger.error("Oracle connection test failed")
            return False
        
        # Test PostgreSQL connection
        if not self.v_postgres_connector.test_connection():
            self.v_logger.error("PostgreSQL connection test failed")
            return False
        
        self.v_logger.info("All database connections successful")
        return True
    
    def validate_configuration(self):
        """Validate sync configuration"""
        self.v_logger.info("Validating sync configuration...")
        
        v_validation_errors = []
        
        # Test database connections
        if not self._test_connections():
            v_validation_errors.append("Database connection test failed")
        
        # Validate table configurations
        for v_table_config in self.v_table_mapping['sync_tables']:
            if not v_table_config.get('v_enabled', True):
                continue
            
            try:
                validate_table_config(v_table_config)
            except ValueError as v_error:
                v_validation_errors.append(f"Table {v_table_config.get('v_table_name', 'Unknown')}: {v_error}")
        
        # Test email notification
        try:
            if not self.v_notification_sender.test_email_connection():
                v_validation_errors.append("Email notification test failed")
        except Exception as v_error:
            v_validation_errors.append(f"Email notification error: {v_error}")
        
        if v_validation_errors:
            self.v_logger.error("Configuration validation failed:")
            for v_error in v_validation_errors:
                self.v_logger.error(f"  - {v_error}")
            return False
        
        self.v_logger.info("Configuration validation successful")
        return True

def main():
    """Main entry point"""
    v_parser = argparse.ArgumentParser(description='Database Synchronization Tool - Oracle to PostgreSQL')
    v_parser.add_argument('--mode', choices=['incremental', 'full', 'validate'], default='incremental',
                         help='Sync mode: incremental, full, or validate')
    v_parser.add_argument('--tables', nargs='+', help='Specific table names to sync')
    v_parser.add_argument('--config', help='Configuration file path')
    v_parser.add_argument('--mapping', help='Table mapping file path')
    
    v_args = v_parser.parse_args()
    
    try:
        # Initialize sync manager
        v_sync_manager = SyncManager(v_args.config, v_args.mapping)
        
        if v_args.mode == 'validate':
            # Validation mode
            if v_sync_manager.validate_configuration():
                print("✅ Configuration validation successful")
                sys.exit(0)
            else:
                print("❌ Configuration validation failed")
                sys.exit(1)
        else:
            # Sync mode
            v_results = v_sync_manager.sync_all_tables(v_args.mode, v_args.tables)
            
            # Check if any sync failed
            v_failed_count = sum(1 for result in v_results if not result.get('v_success', True))
            
            if v_failed_count > 0:
                print(f"❌ Sync completed with {v_failed_count} failures")
                sys.exit(1)
            else:
                print("✅ Sync completed successfully")
                sys.exit(0)
    
    except Exception as v_error:
        print(f"❌ Sync failed: {v_error}")
        logging.getLogger('db_sync').error(f"Main execution failed: {v_error}")
        sys.exit(1)

if __name__ == '__main__':
    main()