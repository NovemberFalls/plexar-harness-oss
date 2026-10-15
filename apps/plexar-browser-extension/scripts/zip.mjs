// Copyright (c) Plexar contributors. Licensed under Apache-2.0.
//
// Minimal store/deflate ZIP writer (no external dependency): walks a
// directory and writes a standard ZIP file readable by Chrome Web Store
// upload and unzip/Explorer. Only the subset of the ZIP format `pack.mjs`
// needs (deflate, no encryption, no Zip64) is implemented.

import { createReadStream } from 'node:fs';
import { readdir, stat, open } from 'node:fs/promises';
import { deflateRawSync } from 'node:zlib';
import { join, relative, sep } from 'node:path';

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++)
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++)
    crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

async function collectFilePaths(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory())
      files.push(...await collectFilePaths(full));
    else if (entry.isFile() && !entry.name.endsWith('.zip'))
      files.push(full);
  }
  return files;
}

async function collectFiles(dir) {
  const files = await collectFilePaths(dir);
  return files.map(f => ({ full: f, rel: relative(dir, f).split(sep).join('/') }));
}

function dosDateTime(date) {
  const time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1);
  const dt = (((date.getFullYear() - 1980) & 0x7f) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { time, dt };
}

/**
 * Zips every file under `sourceDir` into `outPath`, storing paths relative to
 * `sourceDir`. Overwrites `outPath` if it already exists.
 * @param {string} sourceDir - Directory whose contents become the archive root.
 * @param {string} outPath - Destination .zip file path.
 * @returns {Promise<void>} Resolves once the archive is fully written.
 */
export async function zipDirectory(sourceDir, outPath) {
  const files = await collectFiles(sourceDir);
  const handle = await open(outPath, 'w');
  const centralRecords = [];
  let offset = 0;

  try {
    for (const { full, rel } of files) {
      const data = await readAll(full);
      const compressed = deflateRawSync(data);
      const crc = crc32(data);
      const { time, dt } = dosDateTime((await stat(full)).mtime);
      const nameBuf = Buffer.from(rel, 'utf8');

      const localHeader = Buffer.alloc(30);
      localHeader.writeUInt32LE(0x04034b50, 0);
      localHeader.writeUInt16LE(20, 4); // version needed
      localHeader.writeUInt16LE(0, 6); // flags
      localHeader.writeUInt16LE(8, 8); // deflate
      localHeader.writeUInt16LE(time, 10);
      localHeader.writeUInt16LE(dt, 12);
      localHeader.writeUInt32LE(crc, 14);
      localHeader.writeUInt32LE(compressed.length, 18);
      localHeader.writeUInt32LE(data.length, 22);
      localHeader.writeUInt16LE(nameBuf.length, 26);
      localHeader.writeUInt16LE(0, 28);

      await handle.write(localHeader);
      await handle.write(nameBuf);
      await handle.write(compressed);

      centralRecords.push({ nameBuf, crc, compressedSize: compressed.length, size: data.length, time, dt, offset });
      offset += localHeader.length + nameBuf.length + compressed.length;
    }

    const centralStart = offset;
    for (const rec of centralRecords) {
      const central = Buffer.alloc(46);
      central.writeUInt32LE(0x02014b50, 0);
      central.writeUInt16LE(20, 4); // version made by
      central.writeUInt16LE(20, 6); // version needed
      central.writeUInt16LE(0, 8); // flags
      central.writeUInt16LE(8, 10); // deflate
      central.writeUInt16LE(rec.time, 12);
      central.writeUInt16LE(rec.dt, 14);
      central.writeUInt32LE(rec.crc, 16);
      central.writeUInt32LE(rec.compressedSize, 20);
      central.writeUInt32LE(rec.size, 24);
      central.writeUInt16LE(rec.nameBuf.length, 28);
      central.writeUInt32LE(rec.offset, 42);
      await handle.write(central);
      await handle.write(rec.nameBuf);
      offset += central.length + rec.nameBuf.length;
    }
    const centralSize = offset - centralStart;

    const end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50, 0);
    end.writeUInt16LE(centralRecords.length, 8);
    end.writeUInt16LE(centralRecords.length, 10);
    end.writeUInt32LE(centralSize, 12);
    end.writeUInt32LE(centralStart, 16);
    await handle.write(end);
  } finally {
    await handle.close();
  }
}

function readAll(path) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    const stream = createReadStream(path);
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('end', () => resolve(Buffer.concat(chunks)));
    stream.on('error', reject);
  });
}
