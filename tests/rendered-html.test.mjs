import assert from 'node:assert/strict';
import test from 'node:test';
test('production route renders the research workspace',async()=>{
  const {default:worker}=await import('../dist/server/index.js');
  const response=await worker.fetch(new Request('http://localhost/',{headers:{accept:'text/html'}}),{ASSETS:{fetch:async()=>new Response('',{status:404})}},{waitUntil(){},passThroughOnException(){}});
  assert.equal(response.status,200);
  const html=await response.text();
  assert.match(html,/冷杉更新研究室/);
  assert.match(html,/样方与更新概览/);
  assert.doesNotMatch(html,/Your site is taking shape|Starter Project|react-loading-skeleton/);
});
