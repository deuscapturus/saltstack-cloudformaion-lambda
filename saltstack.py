#!/usr/bin/python3
'''
Send a message to a SaltStack API modified for AWS Lambda to be used as an AWS Cloudformation Custom Resource

TODO:
    - figure out what inputs the event will have for cloudformation custom resources
    - figure out what outputs we should have for cloudformation custom resources
'''
import urllib.request, urllib.parse, urllib.error, json, ssl, sys
from botocore.vendored import requests

try:
    import salt.output as salt_outputter
except ImportError:
    raise ImportError("the salt python module is required.  Install it with 'pip install salt' on the TeamCity agent.  The salt-minion and salt-master packages are not required.")

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
    responseBody['PhysicalResourceId'] = physicalResourceId or context.log_stream_name
    responseBody['StackId'] = event['StackId']
    responseBody['RequestId'] = event['RequestId']
    responseBody['LogicalResourceId'] = event['LogicalResourceId']
    responseBody['Data'] = data

    json_responseBody = json.dumps(responseBody)
   
    print("Response body:\n{}".format(json_responseBody))

    headers = {
        'content-type' : '', 
        'content-length' : str(len(json_responseBody))
    }
    
    try:
        response = requests.put(responseUrl,
                                data=json_responseBody,
                                headers=headers)
        print("Status code: {}".format(response.reason))
    except Exception as e:
        raise SystemExit("{}".format(e))

    if status != "SUCCESS":
        sys.exit(1)
    else:
        sys.exit(0)

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
    Execute the restful call to the saltmaster
    '''
    #Login and get a token
    token = get_token()
    headers = { 'X-Auth-Token' : token, 'Accept' : 'application/json', 'Content-Type' : 'application/json' }
    data = urllib.parse.urlencode(args).encode("utf-8")

    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    request = urllib.request.Request(salturl, data, headers=headers)

    try: 
        d = urllib.request.urlopen(request, timeout=3600, context=context).read()
    except urllib.error.HTTPError as e:
        print("Error in API Call: " + e.read())
        return_s3_response("FAILED", data=None, reason=e.read())
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Error in API Call: {}" + str(e.reason))
        return_s3_response("FAILED", data=None, reason=e.reason())
        sys.exit(1)
    except: 
        print("Error Getting in API Call")
        return_s3_response("FAILED", data=None, reason="Unknown error in salt-api request")
        sys.exit(1)

    #print("Raw Return:" +d)
    try:
        return json.loads(d)
    except:
    #TODO: Cannot exit for failure.  must send s3 object with status code and REASON
        print("Return data is not JSON")
        sys.exit(1)
def get_token():
    '''
    Login and get a auth token from the salt master
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
        print("Error Getting Token: {}".format(e.read()))
        return_s3_response("FAILED", data=None, reason=e.read())
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Error Getting Token: " + str(e.reason))
        return_s3_response("failed", data=none, reason=e.reason())
        sys.exit(1)
    except:
        print("Error Getting Token")
        return_s3_response("FAILED", data=None, reason="Unknown error in salt-api auth token request")
        sys.exit(1)

def normalize_local(results):
    '''
    Data is returned in different structure when in batch mode: https://github.com/saltstack/salt/issues/32459
    Make these results the same shape as batch returns here
    '''
    e = {"return": []}
    for key, value in results['return'][0].iteritems():
        e['return'].append({key:value })
    return e

def valid_return(return_data):
    '''
    Check the return data for any failures.  Since every salt module returns data in a different manner this will be hard to do accurately.
    1.  If the function is a state.appply, state.sls or state.highstate return true only if all state id's return true
    2.  For any other function look for a return of true
    *.  Otherwise return false
    '''

    failure = 0
    if function.startswith('state'):
        if type(return_data) is not dict:
            if type(return_data) is list:
                for error in return_data:
                    sys.stderr.write(error+'\n')
            elif type(return_data) is str:
                sys.stderr.write(return_data)
            failure = 1
        else:
            if return_data['return']:
                for miniondata in return_data['return']:
                    for minion, data in miniondata.iteritems():
                        if type(data) is not dict:
                            sys.stderr.write(minion+': '+str(data)+'\n')
                            failure = 1
                        else:
                            if "retcode" in data:
                                if data["retcode"] != 0:
                                    failure = 1
                            else:
                                for state, results in data.iteritems():
                                    if results['result'] == False:
                                        failure = 1
            else:
                sys.stderr.write('ERROR: No minions responded\n')
                failure = 1
    else:
        for miniondata in return_data['return']:
            for minion, data in miniondata.iteritems():
                if data == False:
                    failure = 1
    return(failure)

def handler(event, context):

    __init__(event)
    
    if saltclient == 'local':
        results = local_client()
    
        if not results:
            sys.stderr.write('ERROR: No return received\n')
            #TODO: Cannot exit for failure.  must send s3 object with status code and REASON
            sys.exit(2)
    
        opts = {"color": True, "color_theme": None, "extension_modules": "/"}
        if state_output == "changes":
            opts.update({"state_verbose": False})
        else:
            opts.update({"state_verbose": True})
        #local returns comes back in a weird shape.  But batch returns are ok.  Juts make all returns look like batch.  I still need to test this with subset
        if not batch_size:
            results = normalize_local(results)
        if function.startswith('state'):
            out="highstate"
        else:
            out=None
    
        for minion_result in results['return']:
            for minion, data in minion_result.iteritems():
                if "ret" in data:
                    data[minion] = data.pop('ret')
                    salt_outputter.display_output(data, out=out, opts=opts)
                else:
                    salt_outputter.display_output(minion_result, out=out, opts=opts)

        sys.exit(valid_return(results))
