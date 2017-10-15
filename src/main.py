#!/usr/bin/python3
'''
Send a message to a SaltStack API modified for AWS Lambda to be used as an AWS Cloudformation Custom Resource
'''
import urllib.request, urllib.parse, urllib.error, json, ssl, sys
from botocore.vendored import requests

try:
    import salt.output as salt_outputter
except ImportError:
    raise ImportError("the salt python module is required.  Install it with 'pip3 install salt' on the TeamCity agent.  The salt-minion and salt-master packages are not required.")

def __init__(e):
    '''
    Set global variables. These values are set by the
    ResourceProperties of the lambda event.
    '''

    global event, response_url, saltclient, salturl, eauth, username, password, batch, target, expr_form, function, arguments, batch_size, subset, kwargs, state_output

    event = e
    saltclient = event['ResourceProperties'].get('SaltClient', 'local')
    salturl = event['ResourceProperties'].get('SaltUrl', 'http://localhost:8080')
    eauth = event['ResourceProperties'].get('Eauth')
    username = event['ResourceProperties'].get('Username')
    password = event['ResourceProperties'].get('Password')
    target = event['ResourceProperties'].get('Target')
    expr_form = event['ResourceProperties'].get('ExprForm')
    function = event['ResourceProperties'].get('Function')
    arguments = event['ResourceProperties'].get('Arguments')
    batch_size = event['ResourceProperties'].get('BatchSize')
    subset = event['ResourceProperties'].get('Subset')
    kwargs = event['ResourceProperties'].get('Kwargs')
    state_output = event['ResourceProperties'].get('StateOutput')

    if batch_size and subset:
        return_s3_response("FAILED", None, 'SALTBATCHSIZE and SALTSUBSET cannot be used together.  Erase one of them please')

def return_s3_response(status, data=None, reason=None):
    '''
    Send response to the presigned s3 bucket provided
    by the lambda event.
    '''

    responseBody = {}
    responseBody['Status'] = status
    responseBody['Reason'] = reason
    responseBody['StackId'] = event['StackId']
    responseBody['RequestId'] = event['RequestId']
    responseBody['LogicalResourceId'] = event['LogicalResourceId']
    responseBody['Data'] = data
    responseUrl = event['ResponseURL']

    json_responseBody = json.dumps(responseBody)
    print("json_responseBody: {}\n\n".format(json_responseBody))
   
    headers = {
        'content-type' : '', 
        'content-length' : str(len(json_responseBody))
    }
    
    try:
        response = requests.put(responseUrl,
                                data=json_responseBody,
                                headers=headers)
    except Exception as e:
        raise SystemExit("{}".format(e))

    if status == "SUCCESS":
        sys.exit(0)
    else:
        sys.exit(1)

def local_client():
    '''
    This will run a normal salt command using the saltstack localclient.
    Example: salt 'minion' some.module
    '''

    args = {
        'tgt': target,
        'expr_form': expr_form,
        'client': 'local',
        'fun': function,
    }
    if kwargs:
        args.update(dict(kwarg.split("=") for kwarg in kwargs.split(" ")))
    if arguments:
        args['arg'] = arguments.split(" ")
    if batch_size:
        args['batch'] = batch_size
        args['client'] = 'local_batch'
    if subset:
        args['sub'] = subset
        args['client'] = 'local_subset'
    return exec_rest_call(args)

def exec_rest_call(args):
    '''
    Execute the API call to the salt-api
    '''

    token = get_token()
    headers = { 'X-Auth-Token' : token, 'Accept' : 'application/json'}
    data = urllib.parse.urlencode(args).encode("utf-8")
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    request = urllib.request.Request(salturl, data, headers=headers)

    try: 
        d = urllib.request.urlopen(request, context=context).read()
    except urllib.error.HTTPError as e:
        sys.stderr.write("Error in request to salt-api: {}".format(e.read()))
        return_s3_response("FAILED", data=None, reason=e.read())
    except urllib.error.URLError as e:
        sys.stderr.write("Error in request to salt-api: {}".format(e.reason))
        return_s3_response("FAILED", data=None, reason=str(e.reason()))

    try:
        return json.loads(d)
    except:
        sys.stderr.write("Return data is not JSON")
        return_s3_response("FAILED", data=None, reason="Return data is not JSON")

def get_token():
    '''
    Get a auth token from the salt-api
    '''

    url = salturl + '/login'
    data = urllib.parse.urlencode({
        'username': username,
        'password': password,
        'eauth': eauth
    }).encode("utf-8")
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)

    try:
        auth = urllib.request.urlopen(url, data, context=context).read()
        return json.loads(auth)['return'][0]['token']
    except urllib.error.HTTPError as e:
        sys.stderr.write("Error Getting Token: {}".format(e.read()))
        return_s3_response("FAILED", data=None, reason=e.read())
    except urllib.error.URLError as e:
        sys.stderr.write("Error Getting Token: " + str(e.reason))
        return_s3_response("failed", data=None, reason=e.reason())

def normalize_local(results):
    '''
    Data is returned in different structure when in batch mode: https://github.com/saltstack/salt/issues/32459
    Make these results the same shape as batch returns here
    '''

    e = {"return": []}
    for key, value in results['return'][0].items():
        e['return'].append({key:value })
    return e

def valid_return(return_data):
    '''
    Check the return data for any failures.  Since every salt module returns data in a different manner this will be hard to do accurately.
    Return false if any function id returns false in state.apply, state.sls or state.highstate
    Return false if any other function returns false
    Otherwise return true
    '''

    failure = False
    if function.startswith('state'):
        if type(return_data) is not dict:
            if type(return_data) is list:
                for error in return_data:
                    sys.stderr.write(error+'\n')
            elif type(return_data) is str:
                sys.stderr.write(return_data)
            failure = True
        else:
            if return_data['return']:
                for miniondata in return_data['return']:
                    for minion, data in miniondata.items():
                        if type(data) is not dict:
                            sys.stderr.write(minion+': '+str(data)+'\n')
                            failure = True
                        else:
                            if "retcode" in data:
                                if data["retcode"] != 0:
                                    failure = True
                            else:
                                for state, results in data.items():
                                    if results['result'] == False:
                                        failure = True
            else:
                sys.stderr.write('ERROR: No minions responded\n')
                failure = True
    else:
        for miniondata in return_data['return']:
            for minion, data in miniondata.items():
                if data == False:
                    failure = True
    return(failure)

def handler(event, context):

    __init__(event)
    
    if saltclient == 'local':
        results = local_client()
    
        if not results:
            sys.stderr.write('ERROR: No return received\n')
            return_s3_response("FAILED", data=None, reason="ERROR: No return received")
    
        opts = {"color": True, "color_theme": None, "extension_modules": "/"}
        if state_output == "changes":
            opts.update({"state_verbose": False})
        else:
            opts.update({"state_verbose": True})
        if not batch_size:
            results = normalize_local(results)
        if function.startswith('state'):
            out="highstate"
        else:
            out=None
    
        for minion_result in results['return']:
            for minion, data in minion_result.items():
                if function.startswith('state'):
                  if "ret" in data:
                      data[minion] = data.pop('ret')
                      salt_outputter.display_output(data, out=out, opts=opts)
                else:
                    salt_outputter.display_output(minion_result, out=out, opts=opts)
        

        failure = valid_return(results)
        
        if failure:
            return_s3_response("FAILED", data=results, reason="False results found in return data")
        else:
            return_s3_response("SUCCESS", data=results)
