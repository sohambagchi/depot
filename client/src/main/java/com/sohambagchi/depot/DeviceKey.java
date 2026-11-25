package com.sohambagchi.depot;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

/**
 * This app's identity to depot: a P-256 key pair in the Android Keystore. The private key never
 * leaves the keystore. depot keeps the public key from enrollment and checks a signature over a
 * fresh nonce for every session.
 */
final class DeviceKey {
    private static final String ALIAS = "depot-device";
    static final String CONTEXT = "depot/1";

    private DeviceKey() {}

    private static KeyStore store() throws GeneralSecurityException {
        try {
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            return ks;
        } catch (java.io.IOException e) {
            throw new GeneralSecurityException(e);
        }
    }

    private static KeyStore ensure() throws GeneralSecurityException {
        KeyStore ks = store();
        if (!ks.containsAlias(ALIAS)) {
            KeyPairGenerator gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            gen.initialize(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
                    .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .build());
            gen.generateKeyPair();
        }
        return ks;
    }

    /** The public key as base64 DER SubjectPublicKeyInfo, the form depot stores. */
    static String publicKey() throws GeneralSecurityException {
        return b64(ensure().getCertificate(ALIAS).getPublicKey().getEncoded());
    }

    /** ECDSA-SHA256 over context, nonce and device id, joined by newlines. */
    static String answer(String nonce, String device) throws GeneralSecurityException {
        PrivateKey key = (PrivateKey) ensure().getKey(ALIAS, null);
        Signature sig = Signature.getInstance("SHA256withECDSA");
        sig.initSign(key);
        sig.update((CONTEXT + "\n" + nonce + "\n" + device).getBytes(StandardCharsets.UTF_8));
        return b64(sig.sign());
    }

    private static String b64(byte[] bytes) {
        return Base64.encodeToString(bytes, Base64.NO_WRAP);
    }
}
