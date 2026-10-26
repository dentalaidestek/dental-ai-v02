const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const args=process.argv.slice(2),port=Number(args[args.indexOf('--port')+1]||4173);
const root=path.resolve(__dirname,'..');
http.createServer((req,res)=>{
 const url=new URL(req.url,'http://terminal.local');
 const file=(url.pathname==='/'||url.pathname==='/screen.html')?path.join(__dirname,'screen.html'):url.pathname.startsWith('/static/')?path.join(__dirname,url.pathname):null;
 if(!file||!file.startsWith(root+path.sep)){res.writeHead(404);return res.end()}
 fs.readFile(file,(err,data)=>{if(err){res.writeHead(404);return res.end()}res.setHeader('content-type',file.endsWith('.css')?'text/css':file.endsWith('.svg')?'image/svg+xml':'text/html;charset=utf-8');res.end(data)});
}).listen(port,'0.0.0.0');
