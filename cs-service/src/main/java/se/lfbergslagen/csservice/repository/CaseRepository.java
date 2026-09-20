package se.lfbergslagen.csservice.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import se.lfbergslagen.csservice.model.Case;

public interface CaseRepository extends JpaRepository<Case, String> {
}
