import http from 'http';

http.get('http://localhost:3000/api/tickets?page=1&updated_since=2022-01-01T00:00:00Z', (res) => {
  let data = '';
  res.on('data', (chunk) => data += chunk);
  res.on('end', () => {
    console.log('Status:', res.statusCode);
    console.log('Length:', data.length);
  });
}).on('error', (err) => {
  console.error('Error:', err.message);
});
