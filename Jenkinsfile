pipeline {

  agent any

  environment {
    CONAN_REVISIONS_ENABLED=1
  }

  stages {
    stage('Conan configuration') {
      steps {
        rtConanClient (id: "myConanClient")
        rtConanRemote (
          name: "conan",
          serverId: "artifactory",
          repo: "conan",
          clientId: "myConanClient",
        )
      }
    }

    stage('Build') {
      steps {
        rtBuildInfo(
          captureEnv: true,
        )
        sh "git log --graph --decorate --oneline --all"
        sh "SEMVER_LOGLEVEL=DEBUG python3 semver/conanfile.py 2>&1"
        rtConanRun(
          clientId: "myConanClient",
          command: "create semver"
        )
        rtConanRun(
          clientId: "myConanClient",
          command: "upload -r conan semver --all --confirm"
        )
        rtPublishBuildInfo (
          serverId: "artifactory"
        )
      }
    }
  }
}
