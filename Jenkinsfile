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
