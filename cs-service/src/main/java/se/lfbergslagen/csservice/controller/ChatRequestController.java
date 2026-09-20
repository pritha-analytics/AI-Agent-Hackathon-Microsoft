package se.lfbergslagen.csservice.controller;

import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import se.lfbergslagen.csservice.dto.CreateChatRequestRequest;
import se.lfbergslagen.csservice.dto.PickupRequest;
import se.lfbergslagen.csservice.dto.ReplyRequest;
import se.lfbergslagen.csservice.model.ChatRequest;
import se.lfbergslagen.csservice.model.ChatRequestStatus;
import se.lfbergslagen.csservice.model.CsRole;
import se.lfbergslagen.csservice.model.RolePermissions;
import se.lfbergslagen.csservice.store.ChatRequestStore;

import java.util.Collection;
import java.util.Map;

/**
 * "Talk to a person" hand-offs from the AI assistant. The assistant (a
 * separate Python app) posts the full chat transcript here when the
 * customer asks for a human; a CS agent picks it up and replies from this
 * app's own UI, and the reply is relayed back into the customer's chat
 * window via the Python app's REST API - two separate applications, one
 * conversation.
 *
 * Only the CS_REP role may see or act on chat hand-offs - enforced here,
 * not just hidden in the UI. /api/chat-requests (create) is the exception:
 * that's called by the AI assistant backend, not a human agent.
 */
@RestController
@RequestMapping("/api/chat-requests")
public class ChatRequestController {

    private final ChatRequestStore store;
    private final RestTemplate restTemplate;
    private final String pythonAppBaseUrl;

    public ChatRequestController(
            ChatRequestStore store,
            RestTemplate restTemplate,
            @Value("${python.app.base-url}") String pythonAppBaseUrl
    ) {
        this.store = store;
        this.restTemplate = restTemplate;
        this.pythonAppBaseUrl = pythonAppBaseUrl;
    }

    private void requireCsRep(String roleHeader) {
        if (roleHeader == null || roleHeader.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Missing X-CS-Role header.");
        }
        CsRole role;
        try {
            role = CsRole.valueOf(roleHeader.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown role '" + roleHeader + "'.");
        }
        if (!RolePermissions.canHandleChatRequests(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, role + " is not authorized for chat hand-offs.");
        }
    }

    @PostMapping
    public ResponseEntity<ChatRequest> create(@Valid @RequestBody CreateChatRequestRequest request) {
        ChatRequest created = store.createOrUpdate(
                request.getSessionId(),
                request.getCustomerSummary(),
                request.getTranscript()
        );
        return ResponseEntity.ok(created);
    }

    @GetMapping
    public Collection<ChatRequest> list(@RequestHeader(value = "X-CS-Role", required = false) String roleHeader) {
        requireCsRep(roleHeader);
        return store.list().stream()
                .sorted((a, b) -> b.getCreatedAt().compareTo(a.getCreatedAt()))
                .toList();
    }

    @GetMapping("/{sessionId}")
    public ResponseEntity<ChatRequest> get(
            @PathVariable String sessionId,
            @RequestHeader(value = "X-CS-Role", required = false) String roleHeader
    ) {
        requireCsRep(roleHeader);
        return store.get(sessionId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{sessionId}/pickup")
    public ResponseEntity<ChatRequest> pickup(
            @PathVariable String sessionId,
            @RequestHeader(value = "X-CS-Role", required = false) String roleHeader,
            @Valid @RequestBody PickupRequest request
    ) {
        requireCsRep(roleHeader);
        return store.get(sessionId)
                .map(r -> {
                    r.setAssignedAgent(request.getAgent());
                    r.setStatus(ChatRequestStatus.IN_PROGRESS);
                    store.save(r);
                    notifyPythonAppOfAssignedAgent(sessionId, request.getAgent());
                    return ResponseEntity.ok(r);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{sessionId}/reply")
    public ResponseEntity<?> reply(
            @PathVariable String sessionId,
            @RequestHeader(value = "X-CS-Role", required = false) String roleHeader,
            @Valid @RequestBody ReplyRequest request
    ) {
        requireCsRep(roleHeader);
        var existing = store.get(sessionId);
        if (existing.isEmpty()) {
            return ResponseEntity.notFound().build();
        }

        String url = pythonAppBaseUrl + "/api/sessions/" + sessionId + "/human-message";
        try {
            restTemplate.postForEntity(
                    url,
                    Map.of("content", request.getMessage(), "agent_name", request.getAgent()),
                    Map.class
            );
        } catch (RestClientException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(Map.of(
                            "error", "Could not reach the AI assistant app to deliver this reply.",
                            "detail", ex.getMessage()
                    ));
        }

        ChatRequest chatRequest = existing.get();
        chatRequest.setAssignedAgent(request.getAgent());
        if (chatRequest.getStatus() != ChatRequestStatus.CLOSED) {
            chatRequest.setStatus(ChatRequestStatus.IN_PROGRESS);
        }
        store.save(chatRequest);
        notifyPythonAppOfAssignedAgent(sessionId, request.getAgent());
        return ResponseEntity.ok(chatRequest);
    }

    /** Best-effort: lets the customer's chat show the real agent's name
     * instead of a generic "typing" placeholder, as soon as a case is
     * picked up - not just once the first reply lands. */
    private void notifyPythonAppOfAssignedAgent(String sessionId, String agentName) {
        String url = pythonAppBaseUrl + "/api/sessions/" + sessionId + "/assign-agent";
        try {
            restTemplate.postForEntity(url, Map.of("agent_name", agentName), Map.class);
        } catch (RestClientException ignored) {
            // Non-critical - the customer will still see the agent's name
            // once an actual reply arrives via /human-message.
        }
    }

    @PostMapping("/{sessionId}/close")
    public ResponseEntity<ChatRequest> close(
            @PathVariable String sessionId,
            @RequestHeader(value = "X-CS-Role", required = false) String roleHeader
    ) {
        requireCsRep(roleHeader);
        return store.get(sessionId)
                .map(r -> {
                    r.setStatus(ChatRequestStatus.CLOSED);
                    store.save(r);
                    return ResponseEntity.ok(r);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
