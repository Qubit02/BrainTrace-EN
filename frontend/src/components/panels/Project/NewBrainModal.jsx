/*
 NewBrainModal.jsx

 새 프로젝트(브레인) 생성 모달 컴포넌트.

 주요 기능:
 1. 구동 환경(cloud/local) 선택 UI 제공
 2. 프로젝트 이름 입력 및 생성 요청
 3. 생성 성공 시 상위(onCreated)로 결과 전달 후 닫기(onClose)

 접근성/UX:
 - 모달이 열리면 입력창 자동 포커스
 - 로딩 상태에서는 버튼 비활성화 및 라벨 변경
 - API 에러 메시지는 친절히 안내
*/
import React, { useEffect, useState, useRef } from "react";
import { createBrain } from "../../../../api/config/apiIndex";
import "./NewBrainModal.css";
import { FaCloud } from "react-icons/fa";
import { MdSecurity } from "react-icons/md";

/**
 * 새 프로젝트(브레인) 생성 모달
 *
 * @param {Object} props
 * @param {() => void} props.onClose - 모달 닫기 콜백
 * @param {(brain: any) => void} props.onCreated - 생성된 브레인 정보를 상위로 전달하는 콜백
 */
export default function NewBrainModal({ onClose, onCreated }) {
  // ===== 상태 =====
  // 프로젝트 이름 상태
  const [name, setName] = useState("");

  // 구동 환경 상태 (cloud 또는 local)
  const [deploymentType, setDeploymentType] = useState("cloud");

  // API 요청 중 여부 상태
  const [loading, setLoading] = useState(false);

  // 입력창 포커스를 위한 ref
  const inputRef = useRef(null);

  // ===== 이펙트 =====
  // 모달 열리면 자동 포커스
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // ===== 핸들러 =====
  /**
   * 생성 버튼/폼 제출 핸들러
   * - 기본 제출 동작을 막고 API 호출을 통해 브레인을 생성합니다.
   * - 성공 시 onCreated로 결과 전달 후 모달을 닫습니다.
   * - 실패 시 사용자에게 에러 메시지를 안내합니다.
   */
  // 생성 버튼 시 실행
  const handleSubmit = async (e) => {
    e.preventDefault(); // 폼 기본 제출 막기
    setLoading(true);
    try {
      // API 요청: 새로운 브레인 생성
      const newBrain = await createBrain({
        brain_name: name,
        deployment_type: deploymentType,
      });

      // 상위 컴포넌트에 전달
      onCreated(newBrain);
      onClose();
    } catch (err) {
      // 에러 메시지 출력
      alert(err.response?.data?.detail ?? "Creation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-back">
      <form className="modal-box" onSubmit={handleSubmit}>
        <div className="modal-header">
          <h3>Create new project</h3>
          <button type="button" onClick={onClose} className="close-button">
            ✕
          </button>
        </div>

        {/* 구동 환경 선택 */}
        <div className="deployment-type-section">
          <h4>Select runtime environment</h4>
          <div className="deployment-options">
            <div
              className={`deployment-option ${
                deploymentType === "cloud" ? "selected" : ""
              }`}
              onClick={() => setDeploymentType("cloud")}
            >
              <div className="deployment-icon">
                <FaCloud size={24} color="#4A90E2" />
              </div>
              <div className="deployment-content">
                <h5>Cloud</h5>
                <p>Use OpenAI GPT models</p>
                <ul>
                  <li>• Fast response</li>
                  <li>• High accuracy</li>
                  <li>• Requires internet</li>
                </ul>
              </div>
            </div>

            <div
              className={`deployment-option ${
                deploymentType === "local" ? "selected" : ""
              }`}
              onClick={() => setDeploymentType("local")}
            >
              <div className="deployment-icon">
                <MdSecurity size={24} color="#FF6B6B" />
              </div>
              <div className="deployment-content">
                <h5>Local</h5>
                <p>Use Ollama local models</p>
                <ul>
                  <li>• Stronger data privacy</li>
                  <li>• Works offline</li>
                  <li>• Uses local resources</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* 프로젝트 이름 입력 */}
        <div className="project-name-section">
          <label htmlFor="project-name">Project name</label>
          <input
            ref={inputRef}
            id="project-name"
            type="text"
            placeholder="Enter project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* 생성 버튼: 입력 없으면 비활성화 */}
        <button type="submit" disabled={loading || !name.trim()}>
          {loading ? "Saving…" : "Create"}
        </button>
      </form>
    </div>
  );
}
