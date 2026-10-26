const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const esbuild = require('esbuild');
const web = path.resolve(__dirname, '../../web');
const output = path.join(web, 'legacy');
fs.mkdirSync(output, {recursive:true});
const hashes = {};
function read(name) {
  const source = fs.readFileSync(path.join(web, name), 'utf8');
  hashes[name] = crypto.createHash('sha256').update(source).digest('hex');
  return source;
}
function transform(source) {
  return esbuild.transformSync(source, {target:'chrome70', minify:true, legalComments:'none'}).code;
}
let html = read('index.html').replace(/(<script\b[^>]*>)([\s\S]*?)(<\/script>)/gi, (all, open, code, close) => {
  if (/\bsrc=/.test(open) || !code.trim()) return all;
  return open + transform(code).replace(/<\/script/gi, '<\\/script') + close;
});
for (const file of ['free-film.js', 'abaj-media.js', 'abaj-launcher.js']) {
  fs.writeFileSync(path.join(output, file), transform(read(file)));
  html = html.replace('/static/' + file, '/static/legacy/' + file);
}
fs.writeFileSync(path.join(output, 'index.html'), html);
fs.writeFileSync(path.join(output, 'sources.json'), JSON.stringify(hashes, null, 2) + '\n');
