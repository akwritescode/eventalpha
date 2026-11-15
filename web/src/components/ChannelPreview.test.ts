import { sanitize } from './ChannelPreview';

describe('sanitize (channel preview HTML)', () => {
  it('keeps the Telegram formatting tags', () => {
    expect(sanitize('<b>NVDA</b> · <i>8-K</i>\n<code>x</code>')).toBe('<b>NVDA</b> · <i>8-K</i><br><code>x</code>');
  });

  it('turns anything else into text', () => {
    expect(sanitize('<img src=x onerror=alert(1)><script>alert(2)</script>hi')).toBe('alert(2)hi');
  });

  it('drops non-http links', () => {
    expect(sanitize('<a href="javascript:alert(1)">x</a>')).toBe('x');
  });

  it('re-escapes link targets so a quote cannot break out of the attribute', () => {
    const out = sanitize('<a href="https://example.com/a&quot; onmouseover=&quot;alert(1)">source</a>');
    const link = new DOMParser().parseFromString(out, 'text/html').querySelector('a')!;
    expect(link.getAttribute('onmouseover')).toBeNull();
    expect(link.getAttribute('href')).toBe('https://example.com/a" onmouseover="alert(1)');
  });
});
