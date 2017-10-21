#!/usr/bin/python3

import boto3
import requests


def generate_url(bucket, filename):
    # Get the service client.
    s3 = boto3.client('s3')
    
    # Generate the URL to get 'key-name' from 'bucket-name'
    url = s3.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': bucket,
            'Key': filename
        }
    )

    return url

if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(description='Generate a presigned S3 Put URL')
    parser.add_argument('--bucket', help='S3 bucket name.')
    parser.add_argument('--filename', help='S3 bucket name.')
    args = parser.parse_args()

    print(generate_url(args.bucket, args.filename))
