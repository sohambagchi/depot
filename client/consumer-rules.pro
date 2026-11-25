# Applied to every app that includes depot's client.
# depot-publish looks for the app's own call to Depot.updatesIntent (its "Check for updates" item),
# so R8 must keep the method under its name and not inline it.
-keep class com.sohambagchi.depot.Depot {
    public static android.content.Intent updatesIntent(android.content.Context);
}
