// http:// で開かれたら https:// へ移る（http ではマイクが使えない。workers.dev は自動で転送しない）
if (location.protocol === 'http:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  location.replace('https://' + location.host + location.pathname + location.search + location.hash);
}
