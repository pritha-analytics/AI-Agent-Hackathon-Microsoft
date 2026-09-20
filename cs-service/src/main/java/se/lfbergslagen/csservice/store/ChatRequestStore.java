package se.lfbergslagen.csservice.store;

import org.springframework.stereotype.Component;
import se.lfbergslagen.csservice.model.ChatMessage;
import se.lfbergslagen.csservice.model.ChatRequest;
import se.lfbergslagen.csservice.model.ChatRequestStatus;
import se.lfbergslagen.csservice.repository.ChatRequestRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

/**
 * Store of "talk to a person" hand-offs from the AI assistant, backed by
 * Spring Data JPA (ChatRequestRepository) - see application.properties for
 * which database. Keyed by the assistant's chat session id. Callers that
 * mutate a ChatRequest returned by get() must call save() afterwards for
 * the change to persist (see ChatRequestController).
 */
@Component
public class ChatRequestStore {

    private final ChatRequestRepository repository;

    public ChatRequestStore(ChatRequestRepository repository) {
        this.repository = repository;
    }

    public ChatRequest createOrUpdate(String sessionId, String customerSummary, List<ChatMessage> transcript) {
        ChatRequest request = repository.findById(sessionId).orElseGet(() -> {
            ChatRequest r = new ChatRequest();
            r.setSessionId(sessionId);
            return r;
        });
        request.setCustomerSummary(customerSummary);
        request.setTranscript(transcript);
        if (request.getStatus() == ChatRequestStatus.CLOSED) {
            request.setStatus(ChatRequestStatus.PENDING);
        }
        return repository.save(request);
    }

    public Optional<ChatRequest> get(String sessionId) {
        return repository.findById(sessionId);
    }

    public Collection<ChatRequest> list() {
        return repository.findAll();
    }

    /** Persists changes made to a ChatRequest previously returned by get(). */
    public ChatRequest save(ChatRequest r) {
        return repository.save(r);
    }
}
