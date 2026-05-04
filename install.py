#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import configparser
import json
from pathlib import Path

class DatabaseSyncInstaller:
    """Installer for Database Sync System"""
    
    def __init__(self):
        self.v_project_name = "python-db-sync"
        self.v_install_dir = f"/opt/{self.v_project_name}"
        self.v_current_dir = os.path.dirname(os.path.abspath(__file__))
        self.v_python_executable = sys.executable
        
    def print_status(self, p_message):
        print(f"[INFO] {p_message}")
    
    def print_success(self, p_message):
        print(f"[SUCCESS] {p_message}")
    
    def print_error(self, p_message):
        print(f"[ERROR] {p_message}")
    
    def print_warning(self, p_message):
        print(f"[WARNING] {p_message}")
    
    def check_requirements(self):
        """Check system requirements"""
        self.print_status("Checking system requirements...")
        
        # Check Python version
        if sys.version_info < (3, 7):
            self.print_error("Python 3.7 or higher is required")
            return False
        
        self.print_success(f"Python version: {sys.version}")
        
        # Check if running as root for installation
        if os.geteuid() != 0:
            self.print_error("Please run installer as root (sudo python3 install.py)")
            return False
        
        # Check required system packages
        v_required_packages = ['python3-pip', 'python3-dev', 'libpq-dev']
        
        for v_package in v_required_packages:
            v_result = subprocess.run(['dpkg', '-l', v_package], 
                                    capture_output=True, text=True)
            if v_result.returncode != 0:
                self.print_warning(f"Package {v_package} not found, installing...")
                v_install_result = subprocess.run(['apt', 'install', '-y', v_package])
                if v_install_result.returncode != 0:
                    self.print_error(f"Failed to install {v_package}")
                    return False
        
        return True
    
    def install_python_dependencies(self):
        """Install Python dependencies"""
        self.print_status("Installing Python dependencies...")
        
        v_requirements_file = os.path.join(self.v_current_dir, 'requirements.txt')
        
        if not os.path.exists(v_requirements_file):
            self.print_error("requirements.txt not found")
            return False
        
        # Install dependencies
        v_result = subprocess.run([
            self.v_python_executable, '-m', 'pip', 'install', '-r', v_requirements_file
        ], capture_output=True, text=True)
        
        if v_result.returncode != 0:
            self.print_error(f"Failed to install dependencies: {v_result.stderr}")
            return False
        
        self.print_success("Python dependencies installed successfully")
        return True
    
    def setup_directories(self):
        """Setup project directories"""
        self.print_status("Setting up project directories...")
        
        # Create installation directory
        os.makedirs(self.v_install_dir, exist_ok=True)
        
        # Copy project files
        for v_item in os.listdir(self.v_current_dir):
            v_source = os.path.join(self.v_current_dir, v_item)
            v_destination = os.path.join(self.v_install_dir, v_item)
            
            if os.path.isdir(v_source):
                if os.path.exists(v_destination):
                    shutil.rmtree(v_destination)
                shutil.copytree(v_source, v_destination)
            else:
                shutil.copy2(v_source, v_destination)
        
        # Set permissions
        os.chmod(os.path.join(self.v_install_dir, 'src', 'sync_manager.py'), 0o755)
        
        # Create log directory
        v_log_dir = os.path.join(self.v_install_dir, 'logs')
        os.makedirs(v_log_dir, exist_ok=True)
        os.chmod(v_log_dir, 0o755)
        
        self.print_success(f"Project installed to: {self.v_install_dir}")
        return True
    
    def configure_database_connections(self):
        """Configure database connections"""
        self.print_status("Configuring database connections...")
        
        v_config_file = os.path.join(self.v_install_dir, 'config', 'config.ini')
        
        print("\\n=== Database Configuration ===")
        
        # Oracle configuration
        print("\\nOracle Source Database:")
        v_oracle_host = input("Oracle Host (default: localhost): ").strip() or "localhost"
        v_oracle_port = input("Oracle Port (default: 1521): ").strip() or "1521"
        v_oracle_service = input("Oracle Service Name (default: ORCL): ").strip() or "ORCL"
        v_oracle_user = input("Oracle Username: ").strip()
        v_oracle_password = input("Oracle Password: ").strip()
        
        if not v_oracle_user or not v_oracle_password:
            self.print_error("Oracle credentials are required")
            return False
        
        # PostgreSQL configuration
        print("\\nPostgreSQL Target Database:")
        v_postgres_host = input("PostgreSQL Host (default: localhost): ").strip() or "localhost"
        v_postgres_port = input("PostgreSQL Port (default: 5432): ").strip() or "5432"
        v_postgres_db = input("PostgreSQL Database: ").strip()
        v_postgres_user = input("PostgreSQL Username: ").strip()
        v_postgres_password = input("PostgreSQL Password: ").strip()
        
        if not v_postgres_db or not v_postgres_user or not v_postgres_password:
            self.print_error("PostgreSQL credentials are required")
            return False
        
        # Email configuration
        print("\\nEmail Notification (optional):")
        v_email_from = input("From Email (optional): ").strip()
        v_email_to = input("To Email (optional): ").strip()
        v_email_password = input("Email Password (optional): ").strip()
        
        # Update configuration file
        v_config = configparser.ConfigParser()
        v_config.read(v_config_file)
        
        # Oracle settings
        v_config.set('oracle_source', 'v_host', v_oracle_host)
        v_config.set('oracle_source', 'v_port', v_oracle_port)
        v_config.set('oracle_source', 'v_service_name', v_oracle_service)
        v_config.set('oracle_source', 'v_username', v_oracle_user)
        v_config.set('oracle_source', 'v_password', v_oracle_password)
        
        # PostgreSQL settings
        v_config.set('postgres_target', 'v_host', v_postgres_host)
        v_config.set('postgres_target', 'v_port', v_postgres_port)
        v_config.set('postgres_target', 'v_database', v_postgres_db)
        v_config.set('postgres_target', 'v_username', v_postgres_user)
        v_config.set('postgres_target', 'v_password', v_postgres_password)
        
        # Email settings
        if v_email_from and v_email_to:
            v_config.set('email_notification', 'v_email_from', v_email_from)
            v_config.set('email_notification', 'v_email_to', v_email_to)
            if v_email_password:
                v_config.set('email_notification', 'v_email_password', v_email_password)
        
        # Update log file path
        v_config.set('logging', 'v_log_file', os.path.join(self.v_install_dir, 'logs', 'sync.log'))
        
        # Save configuration
        with open(v_config_file, 'w') as v_file:
            v_config.write(v_file)
        
        self.print_success("Database configuration updated")
        return True
    
    def setup_cronjobs(self):
        """Setup cronjobs for automatic sync"""
        self.print_status("Setting up cronjobs...")
        
        v_sync_script = os.path.join(self.v_install_dir, 'src', 'sync_manager.py')
        
        print("\\n=== Cronjob Configuration ===")
        print("1. Incremental sync every 30 minutes")
        print("2. Full sync weekly (Sunday 2 AM)")
        print("3. Custom schedule")
        print("4. Skip cronjob setup")
        
        v_choice = input("Choose option (1-4): ").strip()
        
        v_cron_entries = []
        
        if v_choice == "1":
            v_cron_entries = [
                f"*/30 * * * * {self.v_python_executable} {v_sync_script} --mode incremental >> {self.v_install_dir}/logs/cron.log 2>&1",
                f"0 2 * * 0 {self.v_python_executable} {v_sync_script} --mode full >> {self.v_install_dir}/logs/cron.log 2>&1"
            ]
        elif v_choice == "2":
            v_cron_entries = [
                f"0 2 * * 0 {self.v_python_executable} {v_sync_script} --mode full >> {self.v_install_dir}/logs/cron.log 2>&1"
            ]
        elif v_choice == "3":
            v_schedule = input("Enter cron schedule (e.g., '0 */6 * * *'): ").strip()
            v_mode = input("Sync mode (incremental/full): ").strip() or "incremental"
            if v_schedule:
                v_cron_entries = [
                    f"{v_schedule} {self.v_python_executable} {v_sync_script} --mode {v_mode} >> {self.v_install_dir}/logs/cron.log 2>&1"
                ]
        elif v_choice == "4":
            self.print_status("Skipping cronjob setup")
            return True
        
        if v_cron_entries:
            # Add cronjobs
            for v_entry in v_cron_entries:
                v_result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
                v_existing_crontab = v_result.stdout if v_result.returncode == 0 else ""
                
                if v_entry not in v_existing_crontab:
                    v_new_crontab = v_existing_crontab + v_entry + "\\n"
                    v_process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
                    v_process.communicate(input=v_new_crontab)
            
            self.print_success("Cronjobs added successfully")
        
        return True
    
    def test_installation(self):
        """Test the installation"""
        self.print_status("Testing installation...")
        
        v_sync_script = os.path.join(self.v_install_dir, 'src', 'sync_manager.py')
        
        # Test configuration validation
        v_result = subprocess.run([
            self.v_python_executable, v_sync_script, '--mode', 'validate'
        ], capture_output=True, text=True, cwd=self.v_install_dir)
        
        if v_result.returncode == 0:
            self.print_success("Installation test successful")
            return True
        else:
            self.print_error(f"Installation test failed: {v_result.stderr}")
            return False
    
    def show_usage_instructions(self):
        """Show usage instructions"""
        print("\\n" + "="*60)
        print("🎉 DATABASE SYNC INSTALLATION COMPLETE!")
        print("="*60)
        print(f"📁 Installation directory: {self.v_install_dir}")
        print(f"📝 Configuration file: {self.v_install_dir}/config/config.ini")
        print(f"📊 Table mapping: {self.v_install_dir}/config/table_mapping.json")
        print(f"📋 Logs directory: {self.v_install_dir}/logs/")
        print()
        print("🔧 Manual Commands:")
        print(f"  Validate config:    {self.v_python_executable} {self.v_install_dir}/src/sync_manager.py --mode validate")
        print(f"  Incremental sync:   {self.v_python_executable} {self.v_install_dir}/src/sync_manager.py --mode incremental")
        print(f"  Full sync:          {self.v_python_executable} {self.v_install_dir}/src/sync_manager.py --mode full")
        print(f"  Specific tables:    {self.v_python_executable} {self.v_install_dir}/src/sync_manager.py --tables employees_sync orders_sync")
        print()
        print("📋 Next Steps:")
        print(f"  1. Edit table mapping: nano {self.v_install_dir}/config/table_mapping.json")
        print(f"  2. Test sync manually: {self.v_python_executable} {self.v_install_dir}/src/sync_manager.py --mode validate")
        print(f"  3. Check logs: tail -f {self.v_install_dir}/logs/sync.log")
        print(f"  4. View cronjobs: crontab -l")
        print()
    
    def install(self):
        """Main installation process"""
        print("="*60)
        print("🚀 DATABASE SYNC INSTALLER")
        print("Oracle → PostgreSQL Synchronization")
        print("="*60)
        
        try:
            if not self.check_requirements():
                return False
            
            if not self.install_python_dependencies():
                return False
            
            if not self.setup_directories():
                return False
            
            if not self.configure_database_connections():
                return False
            
            if not self.setup_cronjobs():
                return False
            
            if not self.test_installation():
                return False
            
            self.show_usage_instructions()
            return True
            
        except KeyboardInterrupt:
            self.print_error("Installation cancelled by user")
            return False
        except Exception as v_error:
            self.print_error(f"Installation failed: {v_error}")
            return False

def main():
    """Main entry point"""
    v_installer = DatabaseSyncInstaller()
    
    if v_installer.install():
        print("\\n✅ Installation completed successfully!")
        sys.exit(0)
    else:
        print("\\n❌ Installation failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()