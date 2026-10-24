/* vera — edit these three values, nothing else.
   safe to commit: the anon key is public by design, row level
   security is what protects the data (see schema.sql). */
window.VERA_CONFIG = {
  supabaseUrl:      "",   // e.g. "https://abcdefgh.supabase.co"
  supabaseAnonKey:  "",   // project settings → api → anon public
  whopCheckoutUrl:  ""    // your whop checkout link
};
/* leave all three empty to run in demo mode:
   the site works and shows the example study, writes nothing. */
