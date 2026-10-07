# ═══════════════════════════════════════════════════════════════════
# 3. DynamoDB Tables
# ═══════════════════════════════════════════════════════════════════
resource "aws_dynamodb_table" "products" {
  name         = "products"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "product_id"
  attribute {
    name = "product_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "orders" {
  name         = "orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"
  attribute {
    name = "order_id"
    type = "S"
  }
}

# ═══════════════════════════════════════════════════════════════════
# 4. S3 Bucket for Product Images
# ═══════════════════════════════════════════════════════════════════
resource "aws_s3_bucket" "product_images" {
  # S3 bucket names must be globally unique, so we append the account ID
  bucket = "ecommerce-product-images-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_cors_configuration" "product_images_cors" {
  bucket = aws_s3_bucket.product_images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# ═══════════════════════════════════════════════════════════════════
# 5. AWS Cognito (User Authentication)
# ═══════════════════════════════════════════════════════════════════
resource "aws_cognito_user_pool" "pool" {
  
  name = "ecommerce-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  schema {
    attribute_data_type = "String"
    name                = "role"
    mutable             = true
    required            = false
  }

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "client" {
  name         = "ecommerce-app-client"
  user_pool_id = aws_cognito_user_pool.pool.id

  generate_secret = true
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]
}

# ═══════════════════════════════════════════════════════════════════
# 6. ECR Repositories
# ═══════════════════════════════════════════════════════════════════
resource "aws_ecr_repository" "services" {
  for_each = toset(["user-service", "product-service", "order-service"])
  
  name                 = each.value
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
