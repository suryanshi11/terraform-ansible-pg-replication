# terraform-ansible-pg-replication
This guide explains how to automate the setup of a PostgreSQL primary-replica architecture using Terraform and Ansible. The API streamlines infrastructure provisioning and configuration for an efficient and scalable database replication setup on AWS.

# Features
- **Infrastructure Automation:** Uses Terraform to provision AWS resources like EC2 instances, security groups, and networking.
- **Configuration Management:** Ansible configures PostgreSQL on primary and replica nodes, sets up replication, and ensures optimal performance.
- **Dynamic Configurations:** Generates Terraform and Ansible files dynamically based on user input.
- **Scalable Architecture:** Designed to add more replicas with minimal effort.
- **API Control:** Exposes an API for setup and management tasks.

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Prerequisites

**System Requirements:**

- Python 3.8+
- Terraform 1.5+
- Ansible 2.12+
- AWS Credentials:
> Ensure aws_access_key_id and aws_secret_access_key are configured in ~/.aws/credentials or exported as environment variables.
