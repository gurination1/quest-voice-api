package com.nyx.vrcaption

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.WindowManager
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.nyx.vrcaption.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var replyJob: Job? = null
    private var lastSubmittedTranscript = ""
    private val conversationHistory = ArrayList<String>()

    private val audioPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                startListening()
            } else {
                binding.statusText.text = getString(R.string.permission_required)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setupUi()
        setupSpeechRecognizer()
    }

    override fun onDestroy() {
        speechRecognizer?.destroy()
        super.onDestroy()
    }

    private fun setupUi() {
        binding.listenButton.setOnClickListener {
            if (isListening) {
                stopListening()
            } else {
                ensureAudioPermissionAndStart()
            }
        }

        binding.clearButton.setOnClickListener {
            conversationHistory.clear()
            lastSubmittedTranscript = ""
            binding.liveSubtitleText.text = ""
            binding.aiReplyText.text = ""
            binding.statusText.text = getString(R.string.ready_status)
        }
    }

    private fun setupSpeechRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            binding.statusText.text = getString(R.string.recognition_not_available)
            binding.listenButton.isEnabled = false
            return
        }

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    binding.statusText.text = getString(R.string.listening_status)
                }

                override fun onBeginningOfSpeech() {
                    binding.statusText.text = getString(R.string.capturing_status)
                }

                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() {
                    binding.statusText.text = getString(R.string.processing_status)
                }

                override fun onError(error: Int) {
                    binding.statusText.text = getString(R.string.retrying_status, error)
                    if (isListening) {
                        restartListeningWithDelay()
                    }
                }

                override fun onResults(results: Bundle?) {
                    val transcript = extractTranscript(results)
                    if (transcript.isNotBlank()) {
                        updateTranscript(transcript, isFinal = true)
                        maybeFetchReply(transcript)
                    }
                    if (isListening) {
                        startRecognizerIntent()
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) {
                    val partialTranscript = extractTranscript(partialResults)
                    if (partialTranscript.isNotBlank()) {
                        updateTranscript(partialTranscript, isFinal = false)
                    }
                }

                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })
        }
    }

    private fun ensureAudioPermissionAndStart() {
        when {
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED -> startListening()
            else -> audioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun startListening() {
        isListening = true
        binding.listenButton.text = getString(R.string.stop_listening)
        binding.statusText.text = getString(R.string.starting_status)
        startRecognizerIntent()
    }

    private fun stopListening() {
        isListening = false
        speechRecognizer?.stopListening()
        binding.listenButton.text = getString(R.string.start_listening)
        binding.statusText.text = getString(R.string.ready_status)
    }

    private fun startRecognizerIntent() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
        }
        speechRecognizer?.startListening(intent)
    }

    private fun restartListeningWithDelay() {
        binding.root.postDelayed({
            if (isListening) {
                startRecognizerIntent()
            }
        }, 450)
    }

    private fun extractTranscript(bundle: Bundle?): String {
        val values = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        return values?.firstOrNull()?.trim().orEmpty()
    }

    private fun updateTranscript(text: String, isFinal: Boolean) {
        val prefix = if (isFinal) getString(R.string.heard_prefix) else getString(R.string.hearing_prefix)
        binding.liveSubtitleText.text = prefix + text
    }

    private fun maybeFetchReply(transcript: String) {
        if (transcript.equals(lastSubmittedTranscript, ignoreCase = true)) {
            return
        }

        lastSubmittedTranscript = transcript
        replyJob?.cancel()
        replyJob = lifecycleScope.launch {
            binding.statusText.text = getString(R.string.reply_status)
            val reply = withContext(Dispatchers.IO) {
                ReplyService.fetchReply(
                    transcript = transcript,
                    history = conversationHistory.toList()
                )
            }
            conversationHistory.add("User: $transcript")
            conversationHistory.add("Assistant: $reply")
            binding.aiReplyText.text = reply
            binding.statusText.text = getString(R.string.listening_status)
        }
    }
}

private object ReplyService {
    fun fetchReply(transcript: String, history: List<String>): String {
        if (BuildConfig.REPLY_API_URL.isBlank()) {
            return offlineReply(transcript)
        }

        return runCatching {
            val connection = (URL(BuildConfig.REPLY_API_URL).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 12_000
                readTimeout = 20_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (BuildConfig.REPLY_API_KEY.isNotBlank()) {
                    setRequestProperty("Authorization", "Bearer ${BuildConfig.REPLY_API_KEY}")
                }
            }

            val payload = JSONObject().apply {
                put("transcript", transcript)
                put("history", JSONArray(history))
                put("mode", "hackathon-vr-caption")
            }

            OutputStreamWriter(connection.outputStream).use { writer ->
                writer.write(payload.toString())
            }

            val responseText = BufferedReader(
                if (connection.responseCode in 200..299) {
                    connection.inputStream.reader()
                } else {
                    connection.errorStream?.reader() ?: throw IllegalStateException("HTTP ${connection.responseCode}")
                }
            ).use { it.readText() }

            val json = JSONObject(responseText)
            json.optString("reply").ifBlank { offlineReply(transcript) }
        }.getOrElse {
            offlineReply(transcript)
        }
    }

    private fun offlineReply(transcript: String): String {
        val compact = transcript.trim().replaceFirstChar {
            if (it.isLowerCase()) {
                it.titlecase(Locale.getDefault())
            } else {
                it.toString()
            }
        }
        val shortText = if (compact.length > 120) compact.take(117) + "..." else compact
        return "Heard: $shortText. Backend is not configured yet, so this is local demo mode."
    }
}
