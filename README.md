# Recipe API

A containerized Python REST API for recipe recommendations, built with FastAPI, Redis, and machine learning models. The API provides semantic search capabilities for recipes and tracks user interactions.

## Features

- Semantic recipe search using sentence transformers
- Redis-based caching and click tracking
- Containerized with Docker
- Kubernetes deployment ready
- Health check endpoints
- Swagger documentation (available at `/docs`)
- Comprehensive test suite

## Prerequisites

- Python 3.12+
- Docker
- Docker Hub account
- kubectl configured with your EKS cluster
- AWS CLI configured
- Redis instance (for production)

## Development Setup

1. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

3. Install production dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
export REDIS_HOST=your-redis-host
export REDIS_PORT=your-redis-port
export REDIS_USERNAME=your-redis-username
export REDIS_PASSWORD=your-redis-password
```

## Running Tests

Run the test suite:
```bash
python -m pytest test.py -v
```

## Running Locally

1. Start the API server:
```bash
uvicorn api:app --reload
```

The API will be available at http://localhost:8000

## Building and Running with Docker

1. Build the Docker image:
```bash
docker build -t your-dockerhub-username/recipe-api:latest ./api
```

2. Run the container locally:
```bash
docker run -p 8000:8000 \
  -e REDIS_HOST=your-redis-host \
  -e REDIS_PORT=your-redis-port \
  -e REDIS_USERNAME=your-redis-username \
  -e REDIS_PASSWORD=your-redis-password \
  your-dockerhub-username/recipe-api:latest
```

## Deploying to Docker Hub

1. Login to Docker Hub:
```bash
docker login
```

2. Push the image:
```bash
docker push your-dockerhub-username/recipe-api:latest
```

## Deploying to Kubernetes

1. Create the Redis secret:
```bash
kubectl apply -f yaml/redis-secret.yaml
```

2. Deploy the application:
```bash
kubectl apply -f yaml/deployment.yaml
kubectl apply -f yaml/service.yaml
kubectl apply -f yaml/ingress.yaml
```

3. Check the deployment status:
```bash
kubectl get deployments
kubectl get pods
kubectl get services
kubectl get ingress
```

## API Endpoints

- `GET /health`: Health check endpoint
- `GET /recipes/query={query}&page={page}`: Get recipes for a given query and page
- `POST /click`: Record click data for analytics

## API Documentation

Once the API is running, you can access the Swagger documentation at:
- Local: http://localhost:8000/docs
- Kubernetes: https://api.recipe-recommendations.com/docs

## Architecture

The API uses:
- FastAPI for the web framework
- Redis for caching and click tracking
- Sentence Transformers for semantic search
- PEFT for model fine-tuning
- Kubernetes for orchestration
- AWS ALB Ingress Controller for load balancing

## Environment Variables

Required environment variables:
- `REDIS_HOST`: Redis server hostname
- `REDIS_PORT`: Redis server port
- `REDIS_USERNAME`: Redis username
- `REDIS_PASSWORD`: Redis password

## AWS Load Balancer Setup

To set up the AWS Load Balancer Controller for the Kubernetes ingress:

1. Get your EKS cluster's OIDC provider ID:
```bash
aws eks describe-cluster --name your-cluster-name --query "cluster.identity.oidc.issuer" --output text
```

2. Create the trust policy file `trust-policy-argo.json`:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/oidc.eks.<REGION>.amazonaws.com/id/<OIDC_PROVIDER_ID>"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_PROVIDER_ID>:sub": "system:serviceaccount:argo:aws-load-balancer-controller",
                    "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_PROVIDER_ID>:aud": "sts.amazonaws.com"
                }
            }
        }
    ]
}
```

3. Replace the placeholders in the trust policy:
- `<AWS_ACCOUNT_ID>`: Your AWS account ID
- `<REGION>`: Your AWS region (e.g., us-east-1)
- `<OIDC_PROVIDER_ID>`: The OIDC provider ID from step 1

4. Create an IAM role for the AWS Load Balancer Controller:
```bash
aws iam create-role \
    --role-name AmazonEKSLoadBalancerControllerRole \
    --assume-role-policy-document file://trust-policy-argo.json
```

5. Attach the AWS Load Balancer Controller policy:
```bash
aws iam attach-role-policy \
    --policy-arn arn:aws:iam::<AWS_ACCOUNT_ID>:policy/AWSLoadBalancerControllerIAMPolicy \
    --role-name AmazonEKSLoadBalancerControllerRole
```

6. Create a Kubernetes service account:
```bash
kubectl create serviceaccount aws-load-balancer-controller -n argo
```

7. Annotate the service account with the IAM role:
```bash
kubectl annotate serviceaccount aws-load-balancer-controller \
    -n argo \
    eks.amazonaws.com/role-arn=arn:aws:iam::<AWS_ACCOUNT_ID>:role/AmazonEKSLoadBalancerControllerRole
```

After completing these steps, the AWS Load Balancer Controller will be able to create and manage load balancers for your Kubernetes ingress resources. 