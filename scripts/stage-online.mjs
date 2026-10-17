import {cp, readFile, rm} from 'node:fs/promises';
// Stage the static frontend for a hosting provider.
const html = await readFile('dist/client/index.html', 'utf8');
if (!html.includes('在线研究工具')) throw new Error('Expected an online frontend build.');
await rm('site', {recursive:true, force:true});
await cp('dist/client', 'site', {recursive:true});
console.log('Online frontend copied to site/ for deployment.');
