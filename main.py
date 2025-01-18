from fastapi import FastAPI, HTTPException
import os
import time
import json
import subprocess
import logging
import boto3
import tempfile
from datetime import datetime  # Import datetime module

# Initialize FastAPI app
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants
OUTPUT_DIR = "output"
AWS_REGION = "ap-southeast-1"  # Set your AWS region
INSTANCE_TAG_NAME = "PostgresPrimary"  # Adjust the tag used for instance identification
KEY_PAIR_NAME = "PostgresKey"  # Name of the key pair to create

# Ensure the output directory exists
if not os.path.exists(OUTPUT_DIR):
    try:
        os.makedirs(OUTPUT_DIR)
        logger.info(f"Created directory: {OUTPUT_DIR}")
    except Exception as e:
        logger.error(f"Failed to create directory {OUTPUT_DIR}: {e}")
        raise

# Initialize AWS EC2 client
ec2_client = boto3.client("ec2", region_name=AWS_REGION)

# Custom JSON serializer to handle datetime objects
def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

# Function to fetch instance IPs based on tags
def fetch_instance_ips():
    instances = ec2_client.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['PostgresPrimary', 'PostgresReplica*']},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    instance_ips = []
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            # Consider instances with a public IP
            public_ip = instance.get('PublicIpAddress')
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            instance_ips.append({
                'id': instance['InstanceId'],
                'ip': public_ip,
                'username': 'ubuntu',
                'tags': tags,
            })
            logger.debug(f"Instance tags: {tags}, Public IP: {public_ip}")
    return instance_ips


# Function to create a temporary PEM file for SSH
def create_temp_pem_file(pem_content):
    try:
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(pem_content.encode())
        temp_file.close()
        logger.info(f"Temporary PEM file created at {temp_file.name}")
        return temp_file.name
    except Exception as e:
        logger.error(f"Error creating temporary PEM file: {e}")
        raise

# Endpoint to generate Terraform and Ansible configurations
@app.post("/generate-code")
async def generate_code(config: dict):
    try:
        # Extract parameters
        postgres_version = config.get("postgres_version", "13")
        instance_type = config.get("instance_type", "t2.micro")
        num_replicas = config.get("num_replicas", 1)
        max_connections = config.get("max_connections", 100)
        shared_buffers = config.get("shared_buffers", "128MB")

        # Generate Terraform configuration
        terraform_config = f"""
        resource "aws_key_pair" "postgres_key" {{
            key_name = "{KEY_PAIR_NAME}"
            public_key = file("~/.ssh/id_rsa.pub")
        }}

        resource "aws_instance" "postgres_primary" {{
            ami           = "ami-06650ca7ed78ff6fa"
            instance_type = "{instance_type}"
            key_name      = aws_key_pair.postgres_key.key_name
            tags = {{
                Name = "PostgresPrimary"
            }}
        }}

        resource "aws_instance" "postgres_replicas" {{
            count         = {num_replicas}
            ami           = "ami-06650ca7ed78ff6fa"
            instance_type = "{instance_type}"
            key_name      = aws_key_pair.postgres_key.key_name
            tags = {{
                Name = "PostgresReplica-${{count.index + 1}}"
            }}
        }}
        """
        terraform_file = os.path.join(OUTPUT_DIR, "main.tf")
        with open(terraform_file, "w") as tf_file:
            tf_file.write(terraform_config)
        logger.info(f"Terraform configuration saved to {terraform_file}")

        # Generate Ansible playbook
        ansible_playbook = f"""
        - name: Setup PostgreSQL replication
          hosts: all
          become: yes
          tasks:
            - name: Install PostgreSQL and dependencies
              apt:
                name:
                  - postgresql
                  - postgresql-contrib
                state: present
                update_cache: yes

            - name: Ensure pip3 is installed
              apt:
                name: python3-pip
                state: present
                update_cache: yes

            - name: Install psycopg2 system package (via apt)
              apt:
                name: python3-psycopg2
                state: present
                update_cache: yes

            - name: Get PostgresSQL version
              command: psql --version
              register: pg_version_output
              changed_when: false

            - name: Parse PostgreSQL version
              set_fact:
                pg_version: "{{{{ pg_version_output.stdout.split(' ')[2].split('.')[0] }}}}"

        - name: Configure primary PostgreSQL server for replication
          hosts: primary
          become: yes
          vars:
            postgres_password: test
            replication_password: rep
          tasks:
            - name: Ensure PostgreSQL service is started and enabled
              service:
                name: postgresql
                state: started
                enabled: yes

            - name: Modify pg_hba.conf to allow trust authentication temporarily
              lineinfile:
                path: /etc/postgresql/{{{{ pg_version }}}}/main/pg_hba.conf
                regexp: '^local\s+all\s+postgres'
                line: "local   all             postgres                                trust"
                state: present

            - name: Reload PostgreSQL to apply changes to pg_hba.conf
              command: systemctl reload postgresql

            - name: Set password for postgres user directly via psql command (with sudo)
              command: sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '{{{{ postgres_password }}}}';"

            - name: Create replication user
              postgresql_user:
                name: replication
                password: "{{{{ replication_password }}}}"
                role_attr_flags: "LOGIN,REPLICATION"
                db: postgres
                state: present
                login_user: postgres
                login_password: "{{{{ postgres_password }}}}"
                login_host: localhost

            - name: Revert pg_hba.conf to md5 authentication for postgres
              lineinfile:
                path: /etc/postgresql/{{{{ pg_version }}}}/main/pg_hba.conf
                regexp: '^local\s+all\s+postgres'
                line: "local   all             postgres                                md5"
                state: present

            - name: Reload PostgreSQL to apply changes to pg_hba.conf
              command: systemctl reload postgresql

            - name: Restart PostgreSQL to apply changes
              service:
                name: postgresql
                state: restarted


        - name: Configure replica PostgreSQL server for replication
          hosts: replica
          become: yes
          tasks:
            - name: Ensure PostgreSQL service is stopped before configuration (if running)
              service:
                name: postgresql
                state: stopped
              when: ansible_facts.services['postgresql'] is defined and ansible_facts.services['postgresql'].state == 'running'

            - name: Remove existing data directory on replica (if any)
              file:
                path: /var/lib/postgresql/{{{{ pg_version }}}}/main
                state: absent
              when: ansible_facts.services['postgresql'] is defined and ansible_facts.services['postgresql'].state == 'stopped'

            - name: Perform base backup from primary server
              command: >
                pg_basebackup -h {{{{ groups['primary'][0] }}}} -U replication -D /var/lib/postgresql/{{{{ pg_version }}}}/main -P -R -X stream
              become: yes
              become_method: sudo
              become_user: postgres
              delegate_to: "{{{{ groups['primary'][0] }}}}"
              environment:
                PGUSER: replication
                PGPASSWORD: "{{{{ replication_password }}}}"
              when: ansible_facts.services['postgresql'] is defined and ansible_facts.services['postgresql'].state == 'stopped'

            - name: Ensure correct file permissions for PostgreSQL directory on replica
              file:
                path: /var/lib/postgresql/{{{{ pg_version }}}}/main
                state: directory
                owner: postgres
                group: postgres
                mode: '0755'
              become: yes
              become_user: root

            - name: Configure recovery.conf for replication on replica
              copy:
                content: |
                  standby_mode = 'on'
                  primary_conninfo = 'host={{{{ groups['primary'][0] }}}} port=5432 user=replication password={{{{ replication_password }}}}'
                  trigger_file = '/tmp/postgresql.trigger.5432'
                dest: /var/lib/postgresql/{{{{ pg_version }}}}/main/recovery.conf
                owner: postgres
                group: postgres
                mode: '0644'

            - name: Start PostgreSQL service on replica
              service:
                name: postgresql
                state: started
        """
        ansible_file = os.path.join(OUTPUT_DIR, "setup.yml")
        with open(ansible_file, "w") as ans_file:
            ans_file.write(ansible_playbook)
        logger.info(f"Ansible playbook saved to {ansible_file}")

        return {"message": "Terraform and Ansible configurations generated successfully"}
    except Exception as e:
        logger.error(f"Error generating configurations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint to plan infrastructure

@app.post("/plan-infrastructure")
async def plan_infrastructure():
    try:
        command = ["terraform", "plan"]
        result = subprocess.run(command, cwd=OUTPUT_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Terraform plan failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=result.stderr)
        return {"message": "Terraform plan successful", "output": result.stdout}
    except Exception as e:
        logger.error(f"Error running Terraform plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# Endpoint to apply Terraform configuration

@app.post("/apply-infrastructure")
async def apply_infrastructure():
    try:
        # Run Terraform apply
        command = ["terraform", "apply", "-auto-approve"]
        result = subprocess.run(command, cwd=OUTPUT_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Terraform apply failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=result.stderr)

        # Retry fetching instance IPs up to 5 times
        for attempt in range(5):
            logger.info(f"Attempt {attempt + 1}/5 to fetch instance IPs...")
            instance_ips = fetch_instance_ips()

            # Filter primary and replica IPs
            primary_ips = [info for info in instance_ips if 'postgresprimary' in info['tags'].get('Name', '').lower()]
            replica_ips = [info for info in instance_ips if 'postgresreplica' in info['tags'].get('Name', '').lower()]

            logger.debug(f"Primary IPs: {primary_ips}")
            logger.debug(f"Replica IPs: {replica_ips}")

            # If all required IPs are fetched, proceed to create the inventory file
            if len(primary_ips) >= 1 and len(replica_ips) >= 1:
                logger.info("Successfully fetched primary and replica IPs.")

                # Create the inventory file
                inventory_file = os.path.join(OUTPUT_DIR, "inventory.ini")
                with open(inventory_file, "w") as inv_file:
                    # Write primary instances to the inventory file
                    inv_file.write("[primary]\n")
                    for info in primary_ips:
                        inv_file.write(f"{info['username']}@{info['ip']} ansible_python_interpreter=/usr/bin/python3\n")

                    # Write replica instances to the inventory file
                    inv_file.write("[replica]\n")
                    for info in replica_ips:
                        inv_file.write(f"{info['username']}@{info['ip']} ansible_python_interpreter=/usr/bin/python3\n")

                    # Write common variables to the inventory file
                    inv_file.write("\n[all:vars]\n")
                    inv_file.write("replication_password=rep\n")

                logger.info(f"Inventory file created at {inventory_file}")

                # Fetch private key content from Terraform output and create a temp PEM file
                private_key_content = subprocess.check_output(
                    ["terraform", "output", "-raw", "private_key"],
                    cwd=OUTPUT_DIR
                ).decode("utf-8")
                private_key_path = create_temp_pem_file(private_key_content)

                # Set the private key path in Ansible configuration
                os.environ["ANSIBLE_PRIVATE_KEY_FILE"] = private_key_path

                return {"message": "Infrastructure applied and inventory file created successfully"}

            # Wait before retrying
            logger.warning(f"Retrying to fetch instance IPs in 15 seconds...")
            time.sleep(15)

        # Raise an exception if unable to fetch required IPs
        logger.error("Failed to fetch instance IPs after multiple retries.")
        raise HTTPException(status_code=500, detail="Failed to fetch instance IPs")

    except Exception as e:
        logger.error(f"Error running Terraform apply: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# Endpoint to configure PostgreSQL
@app.post("/configure-database")
async def configure_database():
    try:
        # Log the start of the command execution
        logger.info("Starting Ansible playbook execution...")
        
        # Run the Ansible playbook with the dynamically created inventory
        command = ["ansible-playbook", "setup.yml", "-i", "inventory.ini"]
        result = subprocess.run(command, cwd=OUTPUT_DIR, capture_output=True, text=True, timeout=3600)  # Added timeout for long-running tasks
        
        # Log the output or error
        logger.info(f"Ansible playbook executed with return code {result.returncode}")
        if result.returncode != 0:
            logger.error(f"Ansible playbook execution failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=result.stderr)
        
        logger.info(f"Ansible playbook output: {result.stdout}")
        return {"message": "Database configuration successful", "output": result.stdout}
    
    except subprocess.TimeoutExpired as e:
        logger.error(f"Ansible playbook execution timed out: {e}")
        raise HTTPException(status_code=500, detail="Ansible playbook execution timed out")
    except Exception as e:
        logger.error(f"Error running Ansible playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
