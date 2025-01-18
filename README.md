# terraform-ansible-pg-replication
This guide explains how to automate the setup of a PostgreSQL primary-replica architecture using Terraform and Ansible. The API streamlines infrastructure provisioning and configuration for an efficient and scalable database replication setup on AWS.

# Features
- **Infrastructure Automation:** Uses Terraform to provision AWS resources like EC2 instances, security groups, and networking.
- **Configuration Management:** Ansible configures PostgreSQL on primary and replica nodes, sets up replication, and ensures optimal performance.
- **Dynamic Configurations:** Generates Terraform and Ansible files dynamically based on user input.
- **Scalable Architecture:** Designed to add more replicas with minimal effort.
- **API Control:** Exposes an API for setup and management tasks.

--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Prerequisites

**System Requirements:**

- Python 3.8+
- Terraform 1.5+
- Ansible 2.12+
- AWS Credentials:
> Ensure aws_access_key_id and aws_secret_access_key are configured in ~/.aws/credentials or exported as environment variables.

--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Installation

**Clone the repository:**

> - git clone [https://github.com/suryanshi11/terraform-ansible-pg-replication.git
](https://github.com/suryanshi11/terraform-ansible-pg-replication.git
)
> - cd terraform-ansible-pg-replication

**Install Python dependencies:**

> pip install -r requirements.txt

--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**Usage**

**1. Start the API**

- Run the FastAPI application:
> uvicorn main:app --reload

- The API will be available at: http://127.0.0.1:8000

**2. Generate Terraform and Ansible Configurations**

- Use a tool like curl or Postman to call the */generate-code* endpoint:
> curl -X POST http://127.0.0.1:8000/generate-code -H "Content-Type: application/json" -d '{
    "postgres_version": "13",
    "instance_type": "t2.micro",
    "num_replicas": 2,
    "max_connections": 200,
    "shared_buffers": "128MB"
}'
- Verify the output/ folder is created and contains:
  - main.tf (Terraform configuration)
  - setup.yml (Ansible playbook)
 
**3. Initialize Terraform**

- Navigate to the output/ folder:
  > cd output
  
  > terraform init

**4. Plan the Infrastructure**

- Call the */plan-infrastructure* endpoint:
  > curl -X POST http://127.0.0.1:8000/plan-infrastructure

**5. Apply the Terraform Configuration**

- Call the */apply-infrastructure* endpoint:
  > curl -X POST http://127.0.0.1:8000/apply-infrastructure
- Confirm infrastructure is created successfully on AWS and inventory.ini file created
   
**6. Configure PostgreSQL**

- Call the */configure-database* endpoint:
> curl -X POST http://127.0.0.1:8000/configure-database
- Verify PostgreSQL is installed and replication is set up on the created instances.


