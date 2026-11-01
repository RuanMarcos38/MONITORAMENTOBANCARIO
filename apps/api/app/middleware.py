"""Bound request bodies before multipart parsing, including chunked uploads."""
from starlette.responses import PlainTextResponse


class RequestBodyLimit:
    def __init__(self, app, maximum=6_000_000):
        self.app=app
        self.maximum=maximum

    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or scope.get('method') in ('GET','HEAD','OPTIONS'):
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        try:
            length=int(headers.get(b'content-length',b'0'))
        except ValueError:
            return await PlainTextResponse('Content-Length inválido',400)(scope,receive,send)
        if length>self.maximum:
            return await PlainTextResponse('Limite de requisição: 6 MB',413)(scope,receive,send)
        messages=[]
        size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            size+=len(message.get('body',b''))
            if size>self.maximum:
                return await PlainTextResponse('Limite de requisição: 6 MB',413)(scope,receive,send)
            messages.append(message)
            if not message.get('more_body'):
                break
        index=0
        async def replay():
            nonlocal index
            if index<len(messages):
                result=messages[index]
                index+=1
                return result
            return await receive()
        return await self.app(scope,replay,send)
