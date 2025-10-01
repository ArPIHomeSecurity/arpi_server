import os
import tempfile
import click

from install.helpers import SystemHelper, PackageHelper, SecurityHelper
from install.installers.base import BaseInstaller

class NginxInstaller(BaseInstaller):
    """Installer for NGINX web server"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.nginx_version = config.get("nginx_version", "1.24.0")
        self.dhparam_file = config.get("dhparam_file", "")
    
    def install_nginx_dependencies(self):
        """Install NGINX build dependencies"""
        click.echo("   📦 Installing NGINX build dependencies...")
        build_deps = ["build-essential", "libpcre3-dev", "libssl-dev", "zlib1g-dev"]
        PackageHelper.install_packages(build_deps, "NGINX build dependencies")
    
    def compile_nginx_from_source(self):
        """Compile and install NGINX from source"""
        click.echo(f"   🔨 Compiling NGINX {self.nginx_version} from source...")
        
        # Check if already installed
        if os.path.exists("/usr/local/nginx/sbin/nginx"):
            click.echo("   ✓ NGINX already installed")
            return
        
        with tempfile.TemporaryDirectory() as temp_dir:
            nginx_archive = f"nginx-{self.nginx_version}.tar.gz"
            nginx_dir = f"nginx-{self.nginx_version}"
            
            # Download NGINX source
            SystemHelper.run_command(
                f"curl -s -O -J http://nginx.org/download/{nginx_archive}",
                cwd=temp_dir
            )
            
            # Extract and compile
            SystemHelper.run_command(f"tar xzf {nginx_archive}", cwd=temp_dir)
            
            nginx_source_dir = os.path.join(temp_dir, nginx_dir)
            
            # Configure build
            SystemHelper.run_command(
                "./configure --with-http_stub_status_module --with-http_ssl_module",
                cwd=nginx_source_dir
            )
            
            # Compile
            SystemHelper.run_command("make", cwd=nginx_source_dir)
            
            # Install
            SystemHelper.run_command("make install", cwd=nginx_source_dir, suppress_output=False)
            
            click.echo("   ✓ NGINX compiled and installed successfully")
    
    def configure_nginx_setup(self):
        """Configure NGINX setup matching bash script"""
        click.echo("   ⚙️ Configuring NGINX setup...")
        
        # Add user www-data to argus group
        try:
            result = SystemHelper.run_command("groups www-data", capture=True, check=False)
            if "argus" not in result.stdout:
                SystemHelper.run_command("adduser www-data argus")
                click.echo("   ✓ Added www-data to argus group")
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: User configuration may have failed: {e}")
            self.warnings.append(f"User configuration may have failed: {e}")
        
        # Remove existing config and copy new one
        SystemHelper.run_command("rm -r /usr/local/nginx/conf/* | true")
        SystemHelper.run_command("cp -r /tmp/server/etc/nginx/* /usr/local/nginx/conf/")
        
        # Create modules-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/modules-enabled/")
        SystemHelper.run_command("ln -s /usr/local/nginx/conf/modules-available/* /usr/local/nginx/conf/modules-enabled/")

        # Create certificate symlink
        SystemHelper.run_command("ln -s /usr/local/nginx/conf/snippets/self-signed.conf /usr/local/nginx/conf/snippets/certificates.conf")

        # Create sites-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/sites-enabled/")
        SystemHelper.run_command("ln -s /usr/local/nginx/conf/sites-available/http.conf /usr/local/nginx/conf/sites-enabled/http.conf")
        SystemHelper.run_command("ln -s /usr/local/nginx/conf/sites-available/local.conf /usr/local/nginx/conf/sites-enabled/local.conf")

        # Copy dhparam file
        SystemHelper.run_command(f"cp {self.dhparam_file} /usr/local/nginx/conf/ssl/")
        click.echo("   ✓ Copied dhparam file")
        
        # Set proper ownership for SSL directory
        SecurityHelper.set_file_permissions("/usr/local/nginx/conf", "www-data:www-data", "755", recursive=True)
        
        click.echo("   ✓ NGINX configuration setup complete")
    
    def install(self):
        """Install NGINX components"""
        self.install_nginx_dependencies()
        self.compile_nginx_from_source()
        self.configure_nginx_setup()
    
    def is_installed(self) -> bool:
        """Check if NGINX is installed"""
        return os.path.exists("/usr/local/nginx/sbin/nginx")
    
    def get_status(self) -> dict:
        """Get NGINX status"""
        return {
            "nginx_installed": os.path.exists("/usr/local/nginx/sbin/nginx"),
            "nginx_configured": os.path.exists("/usr/local/nginx/conf/sites-enabled/http.conf"),
            "nginx_config_valid": SystemHelper.run_command("/usr/local/nginx/sbin/nginx -t", check=False).returncode == 0,
            "nginx_running": SystemHelper.is_service_running("nginx")
        }
