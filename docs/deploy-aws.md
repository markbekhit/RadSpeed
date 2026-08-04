# RadSpeed on AWS

RadSpeed runs as the existing Docker application on one AWS Lightsail server in
Sydney. Caddy terminates HTTPS, application data lives below
`/opt/radspeed/data`, and ECR stores immutable deployment images. Automatic
Lightsail snapshots provide the rollback copy of the server and data.

The CloudFormation template in `deploy/aws/cloudformation.yml` owns the server,
static IP, ECR repository, GitHub OIDC deployment role, and a US$15 Lightsail
budget warning. The server plan is `micro_3_2`: 2 vCPUs, 1 GB RAM and 40 GB SSD
for US$7 per month before snapshot storage and data overages.

GitHub Actions receives short-lived AWS credentials through OIDC. It opens SSH
only to the current GitHub runner, deploys the new image, verifies `/health`, and
closes SSH again. No long-lived AWS access keys are stored in GitHub.

## Migration order

1. Deploy the CloudFormation stack and set the GitHub repository variables.
2. Copy the current Fly.io `/data` directory and environment into the stopped
   AWS application.
3. Run the manual **Deploy to AWS** workflow and verify the static IP.
4. Perform one final SQLite/data sync, change DNS, and verify Google sign-in.
5. Stop Fly.io after DNS traffic reaches AWS; keep it briefly as a rollback,
   then delete its machines and volumes when the AWS copy is proven.

Never use real patient images for deployment testing. Use the synthetic test
fixtures or an explicitly de-identified public case.
