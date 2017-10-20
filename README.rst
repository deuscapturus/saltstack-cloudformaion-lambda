SaltStack Lambda Client for AWS Cloudformation Custom Resource
==============================================================

Testing
-------

pip3 install python-lambda-local

python-lambda-local -t 30 src/main.py event.json

Build
-----

# NOTE: S3 Bucket must already exist
# Set any required AWS CLI env variables. http://docs.aws.amazon.com/cli/latest/userguide/cli-environment.html

  ./build.sh

  export S3BUCKET=mybucket

  aws cloudformation package \
    --template deploy-lambda.yaml \
    --s3-bucket $S3BUCKET \
    --output-template-file packaged-deploy-lambda.yaml

Deploy
------

  aws cloudformation deploy \
    --template-file packaged-deploy-lambda.yaml \
    --stack-name saltstack-cloudformation-lambda \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      SecurityGroup=id-12121212 \
      SubnetID=id-121212

Run
---

# NOTE: Your VPC must have access to S3.  Make sure it has a NAT gateway or a VPC endpoint to s3.

  aws cloudformation deploy \
    --template-file resource-example.yaml \
    --parameter-overrides \
      LambdaARN=arn:aws:lambda:us-west-2:7333333330:function:saltstack-cloudformation-lambda-Lamba-1Qesdfsdfsd
      SaltUrl=http://salt-master:8000 \
      Eauth=pam \
      Username=user \
      Password=password \
      Target=* \
      ExprForm=glob \
      Function=state.apply \
      Arguments=test

References
----------

python-lambda-local: https://pypi.python.org/pypi/python-lambda-local
AWS lambda Python: http://docs.aws.amazon.com/lambda/latest/dg/python-programming-model.html
AWS Cloudformation Custom Resources: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-cfn-customresource.html

