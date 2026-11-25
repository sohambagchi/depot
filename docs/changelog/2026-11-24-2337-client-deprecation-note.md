# depot's client builds without javac's deprecation note

- `Checker.checkArchive` suppresses the deprecation warning for `GET_SIGNATURES`, which it requests on purpose: some Android releases fill only that field for a downloaded APK. airlock-mobile's build reported the note.
