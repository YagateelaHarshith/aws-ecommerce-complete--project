terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS Cluster name"
  default     = "ecommerce-cluster"
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# ═══════════════════════════════════════════════════════════════════
# 1. VPC Configuration (Network for EKS)
# ═══════════════════════════════════════════════════════════════════
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "ecommerce-vpc"
  cidr = "10.0.0.0/16"

  # Need at least 2 AZs for EKS
  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ═══════════════════════════════════════════════════════════════════
# 2. Amazon EKS Cluster
# ═══════════════════════════════════════════════════════════════════
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.35"

  cluster_endpoint_public_access = true

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    main = {
      min_size     = 2
      max_size     = 5
      desired_size = 3

      instance_types = ["t3.small"]
    }
  }

  enable_cluster_creator_admin_permissions = true
}
