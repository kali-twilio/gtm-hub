<div class="min-h-screen flex flex-col items-center px-4 py-14">

  <div class="text-center mb-8 w-full hub-container">
    <h1 style="font-size:40px;font-weight:800;color:var(--text);letter-spacing:-0.02em">SE Forecast</h1>
    <div style="width:40px;height:3px;background:var(--red);border-radius:2px;margin:10px auto 0"></div>
  </div>

  <!-- WIP sticker -->
  <div class="w-full hub-container" style="margin-top:40px;display:flex;justify-content:center">
    <div style="
      display:inline-flex;flex-direction:column;align-items:center;gap:10px;
      background:repeating-linear-gradient(
        -45deg,
        #f5a623,
        #f5a623 18px,
        #1a1a1a 18px,
        #1a1a1a 36px
      );
      border-radius:12px;padding:32px 48px;
      box-shadow:0 8px 32px rgba(0,0,0,0.25),inset 0 1px 0 rgba(255,255,255,0.1);
      border:3px solid #f5a623;
    ">
      <div style="font-size:52px;line-height:1">🚧</div>
      <div style="font-size:28px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;color:#f5a623;text-shadow:0 2px 8px rgba(0,0,0,0.6);background:#1a1a1a;padding:8px 24px;border-radius:6px;border:2px solid #f5a623">
        WORK IN PROGRESS
      </div>
      <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#1a1a1a;background:#f5a623;padding:4px 14px;border-radius:4px">
        Check back soon
      </div>
    </div>
  </div>

</div>

<style>
.hub-container {
  max-width: 32rem;
}
@media (min-width: 768px) {
  .hub-container { max-width: 720px; }
}
@media (min-width: 1024px) {
  .hub-container { max-width: 860px; }
}
</style>
